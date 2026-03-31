import asyncio
import json
import os
import uuid
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv

from fastapi import HTTPException
from models import FlowRequest, DetectRequest, SceneName, AIName, StepResponse
from flow_executor import execute_flow, execute_scorer, _call_ai, _get_api_key, _build_prompt
from scene_router import get_scene_config, SCENE_META
from scene_detector import detect_scene
import db

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await db.create_pool()
    if pool:
        await db.init_db(pool)
        app.state.pool = pool
        logger.info("データベース接続成功")
    else:
        app.state.pool = None
        logger.warning("DB 未接続。DB なしで動作します")
    yield
    if app.state.pool:
        await app.state.pool.close()
        logger.info("データベース接続クローズ")


app = FastAPI(title="AI Scene Router", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "db": app.state.pool is not None,
    }


@app.post("/api/scene/detect")
async def scene_detect(body: DetectRequest):
    """Gemini-flash でシーンを自動判定して返す。"""
    result = await detect_scene(body.question, body.gemini_api_key)
    return result


@app.get("/api/scenes")
async def get_scenes():
    """全シーン定義の一覧を返す。"""
    return SCENE_META


@app.get("/api/config")
async def get_config():
    """現在のデフォルトモデル設定を返す。"""
    return {
        "default_models": {
            "Claude":  os.getenv("DEFAULT_MODEL_CLAUDE",  "claude-opus-4-5"),
            "ChatGPT": os.getenv("DEFAULT_MODEL_CHATGPT", "gpt-4o"),
            "Gemini":  os.getenv("DEFAULT_MODEL_GEMINI",  "gemini-2.5-flash"),
            "Grok":    os.getenv("DEFAULT_MODEL_GROK",    "grok-3-mini"),
        }
    }


@app.post("/api/flow/stream")
async def flow_stream(request_body: FlowRequest, request: Request):
    """SSE エンドポイント。フローの進行をリアルタイムにストリーミング。"""
    scene_config = get_scene_config(request_body.scene)
    pool = app.state.pool
    job_id = str(uuid.uuid4())

    if pool:
        await db.save_job(pool, job_id, request_body.question, request_body.scene.value)

    queue: asyncio.Queue = asyncio.Queue()

    async def on_step(resp):
        await queue.put(("step", resp))

    async def on_score(score):
        await queue.put(("score", score))

    async def run_and_signal():
        try:
            step_responses = await execute_flow(
                request_body, scene_config, on_step, pool, job_id
            )
            if request_body.enable_scorer:
                await execute_scorer(
                    request_body, step_responses, on_score, pool, job_id
                )
        except Exception as e:
            logger.error(f"フロー実行エラー: {e}")
        finally:
            await queue.put(None)

    asyncio.create_task(run_and_signal())

    async def generate() -> AsyncGenerator[str, None]:
        total_steps = 0
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
                if item is None:
                    if pool:
                        await db.finish_job(pool, job_id)
                    yield f"data: {json.dumps({'type': 'complete', 'total_steps': total_steps, 'job_id': job_id}, ensure_ascii=False)}\n\n"
                    break

                kind, obj = item

                if kind == "step":
                    resp_dict = obj.model_dump()
                    resp_dict["ai"] = obj.ai.value
                    resp_dict["role"] = obj.role.value
                    # step_start は SSE 上の擬似イベントとして送らず、step_complete のみ送信
                    yield f"data: {json.dumps({'type': 'step_complete', 'step_index': obj.step_index, 'ai': obj.ai.value, 'role': obj.role.value, 'data': resp_dict}, ensure_ascii=False)}\n\n"
                    total_steps += 1

                elif kind == "score":
                    score_dict = obj.model_dump()
                    score_dict["scorer_ai"] = obj.scorer_ai.value
                    score_dict["target_ai"] = obj.target_ai.value
                    yield f"data: {json.dumps({'type': 'score_complete', 'data': score_dict}, ensure_ascii=False)}\n\n"

            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    logger.info("クライアント切断を検出")
                    break
                yield ": keepalive\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/debate/retry/{job_id}/{ai_name}/{step_id}")
async def retry_step(job_id: str, ai_name: str, step_id: str, request: Request):
    """
    指定ステップを単体で再実行して SSE で結果を返す。
    DB からジョブのコンテキスト（前ステップ結果）を復元して使用する。
    529/500/503 は最大 4 回・指数バックオフでリトライ。タイムアウト 60 秒。
    """
    pool = app.state.pool

    # ── コンテキスト復元 ──
    ctx = await db.get_job_context(pool, job_id) if pool else {}
    if not ctx:
        raise HTTPException(status_code=404, detail=f"job {job_id} が見つかりません")

    job = ctx["job"]
    scene_name = job.get("scene", "")
    question   = job.get("question", "")

    try:
        scene_enum = SceneName(scene_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"不明なシーン: {scene_name}")

    scene_config = get_scene_config(scene_enum)

    # 対象ステップの FlowStep を特定
    target_flow_step = next(
        (s for s in scene_config.steps if s.ai.value == ai_name), None
    )
    if target_flow_step is None:
        raise HTTPException(status_code=404, detail=f"AI {ai_name} がシーン {scene_name} に見つかりません")

    # DB の前ステップ結果を StepResponse 風の dict に変換
    db_steps = {row["step_index"]: row for row in ctx.get("steps", [])}

    # depends_on の content を復元
    class _FakeResp:
        def __init__(self, row):
            self.content = row.get("content") or ""
            self.error   = row.get("error")

    completed = {idx: _FakeResp(db_steps[idx]) for idx in db_steps}

    # フロントから api_key を受け取るため query param で受け取る
    params = dict(request.query_params)
    fake_request = type("R", (), {
        "question":          question,
        "anthropic_api_key": params.get("anthropic_api_key", ""),
        "openai_api_key":    params.get("openai_api_key", ""),
        "gemini_api_key":    params.get("gemini_api_key", ""),
        "grok_api_key":      params.get("grok_api_key", ""),
        "language":          params.get("language", "ja"),
        "model_overrides":   {},
    })()

    try:
        ai_enum = AIName(ai_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"不明な AI: {ai_name}")

    api_key = _get_api_key(ai_enum, fake_request)
    model   = ""
    max_tokens = 2000 if target_flow_step.role.value == "lead" else 1500
    prompt  = _build_prompt(target_flow_step, question, completed, fake_request.language)

    async def generate() -> AsyncGenerator[str, None]:
        # 指数バックオフリトライ（最大 4 回、対象: 529/500/503）
        content = ""
        error   = None
        for attempt in range(5):  # 初回 + 4 回リトライ
            try:
                content = await asyncio.wait_for(
                    _call_ai(ai_enum, prompt, max_tokens, fake_request.language, model, api_key),
                    timeout=60.0,
                )
                error = None
                break
            except asyncio.TimeoutError:
                error = "タイムアウト（60秒）"
                break
            except Exception as e:
                msg = str(e)
                # 529/500/503 はリトライ対象
                retryable = any(code in msg for code in ["529", "500", "503", "overloaded", "server_error"])
                if retryable and attempt < 4:
                    wait = 2 ** attempt
                    logger.warning(f"リトライ {attempt+1}/4: {msg}。{wait}秒後に再試行")
                    await asyncio.sleep(wait)
                    continue
                error = msg
                break

        import time as _time
        resp = StepResponse(
            id=step_id,
            step_index=target_flow_step.step_index,
            ai=ai_enum,
            role=target_flow_step.role,
            content=content,
            error=error,
            timestamp=_time.time(),
        )

        # DB を更新
        if pool:
            await db.update_step_response(pool, step_id, content, error)

        resp_dict = resp.model_dump()
        resp_dict["ai"]   = resp.ai.value
        resp_dict["role"] = resp.role.value
        yield f"data: {json.dumps({'type': 'step_complete', 'step_index': resp.step_index, 'ai': resp.ai.value, 'role': resp.role.value, 'data': resp_dict}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'complete'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/history")
async def get_history():
    """最近 20 件のジョブ一覧。"""
    pool = app.state.pool
    if not pool:
        return []
    return await db.get_recent_jobs(pool) or []


@app.get("/api/history/{job_id}")
async def get_job_history(job_id: str):
    """指定ジョブの全ステップ回答・スコア。"""
    pool = app.state.pool
    if not pool:
        return {"error": "DB not connected"}
    return await db.get_job_detail(pool, job_id) or {}

import asyncio
import json
import uuid
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv

from models import FlowRequest, DetectRequest, SceneName
from flow_executor import execute_flow, execute_scorer
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

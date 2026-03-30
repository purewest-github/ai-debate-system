import asyncio
import json
import uuid
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv

from models import AIName, DebateConfig, DebateResponse
from debate import run_debate
import db

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時: DB 接続プールを作成
    pool = await db.create_pool()
    if pool:
        await db.init_db(pool)
        app.state.pool = pool
        logger.info("データベース接続成功")
    else:
        app.state.pool = None
        logger.warning("DB 未接続。DB なしで動作します")

    yield

    # シャットダウン時: プールをクローズ
    if app.state.pool:
        await app.state.pool.close()
        logger.info("データベース接続クローズ")


app = FastAPI(title="AI Debate System", version="2.0.0", lifespan=lifespan)

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
        "version": "2.0.0",
        "db_connected": app.state.pool is not None,
    }


@app.post("/api/debate/stream")
async def debate_stream(config: DebateConfig, request: Request):
    """SSE エンドポイント。討論の進行をリアルタイムにストリーミング。"""
    # APIキーバリデーション（UI入力もenv変数も空なら400）
    missing = []
    if AIName.CLAUDE in config.enabled_ais and not config.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("Anthropic")
    if AIName.CHATGPT in config.enabled_ais and not config.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        missing.append("OpenAI")
    if AIName.GEMINI in config.enabled_ais and not config.gemini_api_key and not os.environ.get("GEMINI_API_KEY"):
        missing.append("Gemini")
    if AIName.GROK in config.enabled_ais and not config.grok_api_key and not os.environ.get("GROK_API_KEY"):
        missing.append("Grok")
    if missing:
        return JSONResponse(
            status_code=400,
            content={"detail": f"APIキーを入力してください: {', '.join(missing)}"},
        )

    queue: asyncio.Queue = asyncio.Queue()
    job_id = str(uuid.uuid4())
    pool = app.state.pool

    if pool:
        await db.save_job(pool, job_id, config.question, config.rounds)

    async def on_response(resp: DebateResponse):
        await queue.put(resp)

    async def run_and_signal():
        try:
            await run_debate(config, on_response, pool, job_id)
        except Exception as e:
            logger.error(f"討論エラー: {e}")
        finally:
            await queue.put(None)  # 終了シグナル

    asyncio.create_task(run_and_signal())

    async def generate() -> AsyncGenerator[str, None]:
        total = 0
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
                if item is None:
                    # 全完了
                    if pool:
                        await db.finish_job(pool, job_id)
                    yield f"data: {json.dumps({'type': 'complete', 'total': total, 'job_id': job_id}, ensure_ascii=False)}\n\n"
                    break

                # DebateResponse を JSON シリアライズ
                resp_dict = item.model_dump()
                resp_dict["ai"] = item.ai.value
                resp_dict["response_type"] = item.response_type.value
                resp_dict["target_ai"] = item.target_ai.value if item.target_ai else None

                yield f"data: {json.dumps({'type': 'response', 'data': resp_dict}, ensure_ascii=False)}\n\n"
                total += 1

            except asyncio.TimeoutError:
                # クライアントが切断していないか確認
                if await request.is_disconnected():
                    logger.info("クライアント切断を検出。ストリーム終了")
                    break
                yield ": keepalive\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/debate/history")
async def get_history():
    """最近 20 件のジョブ一覧。DB 未接続時は空リスト。"""
    pool = app.state.pool
    if not pool:
        return []
    jobs = await db.get_recent_jobs(pool)
    return jobs or []


@app.get("/api/debate/history/{job_id}")
async def get_job_history(job_id: str):
    """指定ジョブの全レスポンス・スコア。"""
    pool = app.state.pool
    if not pool:
        return {"error": "DB not connected"}
    result = await db.get_job_responses(pool, job_id)
    return result or {}

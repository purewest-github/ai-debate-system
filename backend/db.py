import os
import logging
from typing import Optional
import asyncpg

logger = logging.getLogger(__name__)


async def create_pool() -> Optional[asyncpg.Pool]:
    """接続プール作成。失敗時は None を返す。"""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        logger.warning("DATABASE_URL が設定されていません。DB なしで起動します")
        return None
    try:
        pool = await asyncpg.create_pool(url, min_size=1, max_size=10)
        logger.info("DB 接続プール作成成功")
        return pool
    except Exception as e:
        logger.warning(f"DB 接続失敗: {e}。DB なしで起動します")
        return None


async def init_db(pool: Optional[asyncpg.Pool]) -> None:
    """テーブルを CREATE TABLE IF NOT EXISTS で作成。"""
    if not pool:
        logger.warning("init_db: pool が None のためスキップ")
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS debate_jobs (
                    id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    max_rounds INT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMPTZ
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_responses (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    ai TEXT NOT NULL,
                    round INT NOT NULL,
                    phase TEXT NOT NULL,
                    response_type TEXT NOT NULL,
                    target_ai TEXT,
                    revision_of TEXT,
                    content TEXT NOT NULL,
                    error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_scores (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    scorer_ai TEXT NOT NULL,
                    target_ai TEXT NOT NULL,
                    is_self BOOLEAN NOT NULL,
                    accuracy FLOAT NOT NULL,
                    evidence FLOAT NOT NULL,
                    consistency FLOAT NOT NULL,
                    coverage FLOAT NOT NULL,
                    usefulness FLOAT NOT NULL,
                    brevity FLOAT NOT NULL,
                    revision_quality FLOAT NOT NULL,
                    weighted_total FLOAT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        logger.info("DB テーブル初期化完了")
    except Exception as e:
        logger.warning(f"init_db 失敗: {e}")


async def save_job(pool: Optional[asyncpg.Pool], job_id: str, question: str, max_rounds: int) -> None:
    if not pool:
        logger.warning("save_job: pool が None のためスキップ")
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO debate_jobs (id, question, max_rounds) VALUES ($1, $2, $3)",
                job_id, question, max_rounds,
            )
    except Exception as e:
        logger.warning(f"save_job 失敗: {e}")


async def finish_job(pool: Optional[asyncpg.Pool], job_id: str) -> None:
    if not pool:
        logger.warning("finish_job: pool が None のためスキップ")
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE debate_jobs SET status='finished', finished_at=NOW() WHERE id=$1",
                job_id,
            )
    except Exception as e:
        logger.warning(f"finish_job 失敗: {e}")


async def save_response(pool: Optional[asyncpg.Pool], job_id: str, resp) -> None:
    if not pool:
        logger.warning("save_response: pool が None のためスキップ")
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO ai_responses
                   (id, job_id, ai, round, phase, response_type, target_ai, revision_of, content, error)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                resp.id,
                job_id,
                resp.ai.value,
                resp.round,
                resp.phase,
                resp.response_type.value,
                resp.target_ai.value if resp.target_ai else None,
                resp.revision_of,
                resp.content,
                resp.error,
            )
    except Exception as e:
        logger.warning(f"save_response 失敗: {e}")


async def save_score(pool: Optional[asyncpg.Pool], job_id: str, score) -> None:
    if not pool:
        logger.warning("save_score: pool が None のためスキップ")
        return
    try:
        import uuid
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO ai_scores
                   (id, job_id, scorer_ai, target_ai, is_self,
                    accuracy, evidence, consistency, coverage, usefulness, brevity, revision_quality,
                    weighted_total, reason)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)""",
                str(uuid.uuid4()),
                job_id,
                score.scorer_ai.value,
                score.target_ai.value,
                score.is_self,
                score.accuracy,
                score.evidence,
                score.consistency,
                score.coverage,
                score.usefulness,
                score.brevity,
                score.revision_quality,
                score.weighted_total,
                score.reason,
            )
    except Exception as e:
        logger.warning(f"save_score 失敗: {e}")


async def get_recent_jobs(pool: Optional[asyncpg.Pool], limit: int = 20) -> list:
    if not pool:
        logger.warning("get_recent_jobs: pool が None のためスキップ")
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM debate_jobs ORDER BY started_at DESC LIMIT $1", limit
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"get_recent_jobs 失敗: {e}")
        return []


async def get_job_responses(pool: Optional[asyncpg.Pool], job_id: str) -> dict:
    if not pool:
        logger.warning("get_job_responses: pool が None のためスキップ")
        return {}
    try:
        async with pool.acquire() as conn:
            job_row = await conn.fetchrow(
                "SELECT * FROM debate_jobs WHERE id=$1", job_id
            )
            if not job_row:
                return {}
            responses = await conn.fetch(
                "SELECT * FROM ai_responses WHERE job_id=$1 ORDER BY created_at", job_id
            )
            scores = await conn.fetch(
                "SELECT * FROM ai_scores WHERE job_id=$1 ORDER BY created_at", job_id
            )
            return {
                "job": dict(job_row),
                "responses": [dict(r) for r in responses],
                "scores": [dict(s) for s in scores],
            }
    except Exception as e:
        logger.warning(f"get_job_responses 失敗: {e}")
        return {}

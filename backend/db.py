import os
import uuid
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
                CREATE TABLE IF NOT EXISTS scene_jobs (
                    id TEXT PRIMARY KEY,
                    question TEXT,
                    scene TEXT,
                    status TEXT DEFAULT 'running',
                    started_at TIMESTAMP DEFAULT NOW(),
                    finished_at TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS step_responses (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    step_index INT,
                    ai TEXT,
                    role TEXT,
                    content TEXT,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS step_scores (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    scorer_ai TEXT,
                    target_ai TEXT,
                    is_self BOOLEAN,
                    accuracy FLOAT,
                    evidence FLOAT,
                    consistency FLOAT,
                    coverage FLOAT,
                    usefulness FLOAT,
                    brevity FLOAT,
                    revision_quality FLOAT,
                    weighted_total FLOAT,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        logger.info("DB テーブル初期化完了")
    except Exception as e:
        logger.warning(f"init_db 失敗: {e}")


async def save_job(pool: Optional[asyncpg.Pool], job_id: str, question: str, scene: str) -> None:
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO scene_jobs (id, question, scene) VALUES ($1, $2, $3)",
                job_id, question, scene,
            )
    except Exception as e:
        logger.warning(f"save_job 失敗: {e}")


async def finish_job(pool: Optional[asyncpg.Pool], job_id: str) -> None:
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE scene_jobs SET status='finished', finished_at=NOW() WHERE id=$1",
                job_id,
            )
    except Exception as e:
        logger.warning(f"finish_job 失敗: {e}")


async def save_response(pool: Optional[asyncpg.Pool], job_id: str, resp) -> None:
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO step_responses
                   (id, job_id, step_index, ai, role, content, error)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                resp.id,
                job_id,
                resp.step_index,
                resp.ai.value,
                resp.role.value,
                resp.content,
                resp.error,
            )
    except Exception as e:
        logger.warning(f"save_response 失敗: {e}")


async def save_score(pool: Optional[asyncpg.Pool], job_id: str, score) -> None:
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO step_scores
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
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM scene_jobs ORDER BY started_at DESC LIMIT $1", limit
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"get_recent_jobs 失敗: {e}")
        return []


async def get_job_context(pool: Optional[asyncpg.Pool], job_id: str) -> dict:
    """リトライ用: job の scene/question と全 step_responses を返す。"""
    if not pool:
        return {}
    try:
        async with pool.acquire() as conn:
            job_row = await conn.fetchrow("SELECT * FROM scene_jobs WHERE id=$1", job_id)
            if not job_row:
                return {}
            steps = await conn.fetch(
                "SELECT * FROM step_responses WHERE job_id=$1 ORDER BY step_index, created_at",
                job_id,
            )
            return {
                "job": dict(job_row),
                "steps": [dict(r) for r in steps],
            }
    except Exception as e:
        logger.warning(f"get_job_context 失敗: {e}")
        return {}


async def update_step_response(
    pool: Optional[asyncpg.Pool], step_id: str, content: str, error: Optional[str]
) -> None:
    """リトライ後に step_responses を上書き更新する。"""
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE step_responses SET content=$1, error=$2 WHERE id=$3",
                content, error, step_id,
            )
    except Exception as e:
        logger.warning(f"update_step_response 失敗: {e}")


async def get_job_detail(pool: Optional[asyncpg.Pool], job_id: str) -> dict:
    if not pool:
        return {}
    try:
        async with pool.acquire() as conn:
            job_row = await conn.fetchrow("SELECT * FROM scene_jobs WHERE id=$1", job_id)
            if not job_row:
                return {}
            steps = await conn.fetch(
                "SELECT * FROM step_responses WHERE job_id=$1 ORDER BY step_index, created_at",
                job_id,
            )
            scores = await conn.fetch(
                "SELECT * FROM step_scores WHERE job_id=$1 ORDER BY created_at", job_id
            )
            return {
                "job": dict(job_row),
                "steps": [dict(r) for r in steps],
                "scores": [dict(s) for s in scores],
            }
    except Exception as e:
        logger.warning(f"get_job_detail 失敗: {e}")
        return {}

import asyncio
import uuid
import time
import logging
from typing import Callable, List, Any

from models import AIName, ResponseType, DebateResponse, ScoreDetail, DebateConfig
from clients import call_claude, call_chatgpt, call_gemini, call_grok
from prompts import initial_prompt, evaluation_prompt, revision_prompt, scoring_prompt_v2
from scorer import parse_score_response, calculate_weighted_total
import db

logger = logging.getLogger(__name__)


async def _call_ai(
    ai: AIName,
    prompt: str,
    config: DebateConfig,
    max_tokens: int,
    semaphore: asyncio.Semaphore,
    model_override: str = "",
) -> str:
    """各 AI クライアントへのディスパッチ。semaphore で同時実行数を制限。"""
    async with semaphore:
        if ai == AIName.CLAUDE:
            result = await call_claude(prompt, max_tokens, config.language, model_override, config.anthropic_api_key)
        elif ai == AIName.CHATGPT:
            result = await call_chatgpt(
                prompt, max_tokens, config.language, model_override, config.openai_api_key
            )
        elif ai == AIName.GEMINI:
            result = await call_gemini(
                prompt, max_tokens, config.language, model_override, config.gemini_api_key
            )
        elif ai == AIName.GROK:
            result = await call_grok(
                prompt, max_tokens, config.language, model_override, config.grok_api_key
            )
        else:
            raise ValueError(f"未知の AI: {ai}")

        # デバッグ: 空/None レスポンスを警告ログに出力
        if not result:
            logger.warning(
                f"[DEBUG] {ai.value} が空またはNoneのレスポンスを返しました。"
                f" model={model_override or 'default'}, max_tokens={max_tokens},"
                f" prompt_head={prompt[:100]!r}"
            )
        return result


async def run_debate(
    config: DebateConfig,
    on_response: Callable,
    pool: Any = None,
    job_id: str = "",
) -> List[DebateResponse]:
    """
    4フェーズのオーケストレーション。
    Phase 0: 初回回答（並列）
    Phase 1..N: 相互評価（並列）
    Phase revision: 自己改訂（並列、enable_revision=True のとき）
    Phase scoring: 採点（並列）
    """
    semaphore = asyncio.Semaphore(4)
    all_responses: List[DebateResponse] = []
    ais = config.enabled_ais

    # -------- Phase 0: 初回回答 --------
    async def do_initial(ai: AIName) -> DebateResponse:
        prompt = initial_prompt(config.question, config.language)
        try:
            content = await _call_ai(ai, prompt, config, config.max_tokens_initial, semaphore, "")
            return DebateResponse(
                id=str(uuid.uuid4()),
                ai=ai,
                round=0,
                response_type=ResponseType.INITIAL,
                phase="initial",
                content=content,
                timestamp=time.time(),
            )
        except Exception as e:
            logger.error(f"{ai.value} 初回回答エラー: {e}")
            return DebateResponse(
                id=str(uuid.uuid4()),
                ai=ai,
                round=0,
                response_type=ResponseType.INITIAL,
                phase="initial",
                content="",
                error=str(e),
                timestamp=time.time(),
            )

    initial_tasks = [do_initial(ai) for ai in ais]
    for coro in asyncio.as_completed(initial_tasks):
        resp = await coro
        all_responses.append(resp)
        await on_response(resp)
        if pool and job_id:
            await db.save_response(pool, job_id, resp)

    # -------- Phase 1..N: 相互評価 --------
    for round_num in range(1, config.rounds + 1):
        snapshot = list(all_responses)

        async def do_evaluation(
            evaluator: AIName, target: AIName, snap=snapshot
        ) -> DebateResponse:
            prev = [
                {"ai": r.ai.value, "content": r.content}
                for r in snap
                if not r.error
                and r.response_type in (ResponseType.INITIAL, ResponseType.EVALUATION)
            ]
            prompt = evaluation_prompt(
                config.question, target.value, prev, round_num, config.language
            )
            try:
                content = await _call_ai(
                    evaluator, prompt, config, config.max_tokens_eval, semaphore, config.model_eval
                )
                return DebateResponse(
                    id=str(uuid.uuid4()),
                    ai=evaluator,
                    round=round_num,
                    response_type=ResponseType.EVALUATION,
                    phase="evaluation",
                    target_ai=target,
                    content=content,
                    timestamp=time.time(),
                )
            except Exception as e:
                logger.error(f"{evaluator.value} → {target.value} 評価エラー: {e}")
                return DebateResponse(
                    id=str(uuid.uuid4()),
                    ai=evaluator,
                    round=round_num,
                    response_type=ResponseType.EVALUATION,
                    phase="evaluation",
                    target_ai=target,
                    content="",
                    error=str(e),
                    timestamp=time.time(),
                )

        eval_tasks = [
            do_evaluation(evaluator, target)
            for evaluator in ais
            for target in ais
            if evaluator != target
        ]
        for coro in asyncio.as_completed(eval_tasks):
            resp = await coro
            all_responses.append(resp)
            await on_response(resp)
            if pool and job_id:
                await db.save_response(pool, job_id, resp)

    # -------- Phase revision: 自己改訂 --------
    if config.enable_revision:
        snapshot = list(all_responses)

        async def do_revision(ai: AIName, snap=snapshot) -> DebateResponse:
            # 自分の初回回答を取得
            my_initial = next(
                (r for r in snap if r.ai == ai and r.response_type == ResponseType.INITIAL),
                None,
            )
            if not my_initial:
                return DebateResponse(
                    id=str(uuid.uuid4()),
                    ai=ai,
                    round=0,
                    response_type=ResponseType.REVISION,
                    phase="revision",
                    content="",
                    error="初回回答が見つかりません",
                    timestamp=time.time(),
                )
            # 自分への評価を収集
            critiques = [
                {"ai": r.ai.value, "content": r.content}
                for r in snap
                if r.response_type == ResponseType.EVALUATION
                and r.target_ai == ai
                and not r.error
            ]
            prompt = revision_prompt(
                config.question, ai.value, my_initial.content, critiques, config.language
            )
            try:
                content = await _call_ai(
                    ai, prompt, config, config.max_tokens_revision, semaphore, config.model_revision
                )
                return DebateResponse(
                    id=str(uuid.uuid4()),
                    ai=ai,
                    round=0,
                    response_type=ResponseType.REVISION,
                    phase="revision",
                    revision_of=my_initial.id,
                    content=content,
                    timestamp=time.time(),
                )
            except Exception as e:
                logger.error(f"{ai.value} 改訂エラー: {e}")
                return DebateResponse(
                    id=str(uuid.uuid4()),
                    ai=ai,
                    round=0,
                    response_type=ResponseType.REVISION,
                    phase="revision",
                    revision_of=my_initial.id,
                    content="",
                    error=str(e),
                    timestamp=time.time(),
                )

        revision_tasks = [do_revision(ai) for ai in ais]
        for coro in asyncio.as_completed(revision_tasks):
            resp = await coro
            all_responses.append(resp)
            await on_response(resp)
            if pool and job_id:
                await db.save_response(pool, job_id, resp)

    # -------- Phase scoring: 採点 --------
    snapshot = list(all_responses)

    async def do_scoring(scorer: AIName, snap=snapshot) -> DebateResponse:
        scored_responses = [
            {"ai": r.ai.value, "phase": r.phase, "content": r.content}
            for r in snap
            if not r.error
            and r.response_type in (ResponseType.INITIAL, ResponseType.REVISION)
        ]
        ai_names = [ai.value for ai in ais]
        prompt = scoring_prompt_v2(
            config.question, scored_responses, ai_names, config.language
        )
        try:
            content = await _call_ai(
                scorer, prompt, config, config.max_tokens_score, semaphore, config.model_scoring
            )
            return DebateResponse(
                id=str(uuid.uuid4()),
                ai=scorer,
                round=0,
                response_type=ResponseType.SCORING,
                phase="scoring",
                content=content,
                timestamp=time.time(),
            )
        except Exception as e:
            logger.error(f"{scorer.value} 採点エラー: {e}")
            return DebateResponse(
                id=str(uuid.uuid4()),
                ai=scorer,
                round=0,
                response_type=ResponseType.SCORING,
                phase="scoring",
                content="",
                error=str(e),
                timestamp=time.time(),
            )

    scoring_tasks = [do_scoring(ai) for ai in ais]
    for coro in asyncio.as_completed(scoring_tasks):
        resp = await coro
        all_responses.append(resp)
        await on_response(resp)

        # スコアをパースして DB に保存
        if not resp.error:
            parsed = parse_score_response(resp.content)
            if parsed and "scores" in parsed:
                ai_map = {ai.value: ai for ai in ais}
                for score_data in parsed["scores"]:
                    target_name = score_data.get("target_ai", "")
                    target_ai = ai_map.get(target_name)
                    if not target_ai:
                        continue
                    is_self = resp.ai == target_ai
                    raw = {
                        "accuracy": float(score_data.get("accuracy", 0)),
                        "evidence": float(score_data.get("evidence", 0)),
                        "consistency": float(score_data.get("consistency", 0)),
                        "coverage": float(score_data.get("coverage", 0)),
                        "usefulness": float(score_data.get("usefulness", 0)),
                        "brevity": float(score_data.get("brevity", 0)),
                        "revision_quality": float(score_data.get("revision_quality", 0)),
                    }
                    weighted = calculate_weighted_total(raw, is_self)
                    score_detail = ScoreDetail(
                        scorer_ai=resp.ai,
                        target_ai=target_ai,
                        is_self=is_self,
                        weighted_total=weighted,
                        reason=score_data.get("reason", ""),
                        **raw,
                    )
                    if pool and job_id:
                        await db.save_score(pool, job_id, score_detail)

        if pool and job_id:
            await db.save_response(pool, job_id, resp)

    return all_responses

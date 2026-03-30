"""
フロー実行エンジン: SceneConfig の FlowStep リストを依存関係に従って実行する。
"""
import asyncio
import uuid
import time
import os
import logging
from typing import Callable, Awaitable

from models import (
    AIName, StepRole, FlowRequest, FlowStep, SceneConfig,
    StepResponse, ScoreDetail,
)
from clients import call_claude, call_chatgpt, call_gemini, call_grok
from prompts import (
    lead_implementation, lead_decision, lead_logic_check, lead_research,
    support_critic, support_organizer, support_validator, support_executor,
    support_rewriter, support_confidence, support_uncertainty, support_hypothesis,
    scoring_prompt,
)
from scorer import parse_score_response, calculate_weighted_total, WEIGHTS
import db

logger = logging.getLogger(__name__)

# デフォルト max_tokens
MAX_TOKENS_LEAD    = 2000
MAX_TOKENS_SUPPORT = 1500
MAX_TOKENS_SCORER  = 3000


def _get_api_key(ai: AIName, request: FlowRequest) -> str:
    """AI に対応する API キーを返す。Claude は環境変数フォールバック。"""
    if ai == AIName.CLAUDE:
        return os.environ.get("ANTHROPIC_API_KEY", "")
    if ai == AIName.CHATGPT:
        return request.openai_api_key
    if ai == AIName.GEMINI:
        return request.gemini_api_key
    if ai == AIName.GROK:
        return request.grok_api_key
    return ""


async def _call_ai(
    ai: AIName, prompt: str, max_tokens: int, language: str, model: str, api_key: str
) -> str:
    """AI クライアントへのディスパッチ。"""
    if ai == AIName.CLAUDE:
        return await call_claude(prompt, max_tokens, language, model, api_key)
    if ai == AIName.CHATGPT:
        return await call_chatgpt(prompt, max_tokens, language, model, api_key)
    if ai == AIName.GEMINI:
        return await call_gemini(prompt, max_tokens, language, model, api_key)
    if ai == AIName.GROK:
        return await call_grok(prompt, max_tokens, language, model, api_key)
    raise ValueError(f"未知の AI: {ai}")


def _get_dep_content(dep_responses: dict, idx: int) -> str:
    """依存ステップの content を返す。エラー時は代替文字列。"""
    resp = dep_responses.get(idx)
    if resp is None or resp.error:
        return "（前ステップでエラーが発生しました）"
    return resp.content


def _build_prompt(
    step: FlowStep,
    question: str,
    dep_responses: dict,
    language: str,
) -> str:
    """prompt_key と depends_on の内容からプロンプトを構築する。"""
    key = step.prompt_key
    deps = {i: _get_dep_content(dep_responses, i) for i in step.depends_on}

    # deps リスト（depends_on の順序通り）
    dep_list = [deps[i] for i in step.depends_on]

    if key == "lead_implementation":
        return lead_implementation(question, language)
    if key == "lead_decision":
        return lead_decision(question, language)
    if key == "lead_logic_check":
        return lead_logic_check(question, language)
    if key == "lead_research":
        return lead_research(question, language)
    if key == "support_critic":
        return support_critic(question, dep_list[0], language)
    if key == "support_organizer":
        return support_organizer(question, dep_list[0], dep_list[1], language)
    if key == "support_validator":
        return support_validator(question, dep_list[0], language)
    if key == "support_executor":
        return support_executor(question, dep_list[0], language)
    if key == "support_rewriter":
        # original_text=question, critic_output=step0
        return support_rewriter(question, dep_list[0], language)
    if key == "support_confidence":
        # original_text=question, critic_output=step0, rewritten=step1
        return support_confidence(question, dep_list[0], dep_list[1], language)
    if key == "support_uncertainty":
        return support_uncertainty(dep_list[0], language)
    if key == "support_hypothesis":
        return support_hypothesis(dep_list[0], language)

    raise ValueError(f"未知の prompt_key: {key}")


async def _execute_step(
    step: FlowStep,
    request: FlowRequest,
    completed: dict,
) -> StepResponse:
    """単一ステップを実行して StepResponse を返す。"""
    dep_responses = {i: completed.get(i) for i in step.depends_on}
    prompt = _build_prompt(step, request.question, dep_responses, request.language)
    api_key = _get_api_key(step.ai, request)
    model = request.model_overrides.get(step.ai.value, "")
    max_tokens = MAX_TOKENS_LEAD if step.role == StepRole.LEAD else MAX_TOKENS_SUPPORT

    try:
        content = await _call_ai(step.ai, prompt, max_tokens, request.language, model, api_key)
        return StepResponse(
            id=str(uuid.uuid4()),
            step_index=step.step_index,
            ai=step.ai,
            role=step.role,
            content=content,
            timestamp=time.time(),
        )
    except Exception as e:
        logger.error(f"{step.ai.value} step{step.step_index} エラー: {e}")
        return StepResponse(
            id=str(uuid.uuid4()),
            step_index=step.step_index,
            ai=step.ai,
            role=step.role,
            content="",
            error=str(e),
            timestamp=time.time(),
        )


async def execute_flow(
    request: FlowRequest,
    scene_config: SceneConfig,
    on_step: Callable[[StepResponse], Awaitable[None]],
    pool,
    job_id: str,
) -> list:
    """
    scene_config.steps の FlowStep リストを依存関係に従って実行する。

    アルゴリズム:
    1. steps を step_index 順にソート
    2. 全依存が完了したステップ群を asyncio.gather で並列実行
    3. 完了後に on_step を呼ぶ
    """
    steps = sorted(scene_config.steps, key=lambda s: s.step_index)
    completed: dict = {}
    all_responses: list = []
    remaining = list(steps)

    while remaining:
        # 全依存が完了しているステップを抽出
        runnable = [s for s in remaining if all(i in completed for i in s.depends_on)]
        if not runnable:
            logger.error("実行可能なステップが見つかりません（循環依存の可能性）")
            break

        runnable_indices = {s.step_index for s in runnable}
        remaining = [s for s in remaining if s.step_index not in runnable_indices]

        # 並列実行
        tasks = [_execute_step(s, request, completed) for s in runnable]
        results = await asyncio.gather(*tasks)

        for resp in results:
            completed[resp.step_index] = resp
            all_responses.append(resp)
            await on_step(resp)
            if pool and job_id:
                await db.save_response(pool, job_id, resp)

    return all_responses


async def execute_scorer(
    request: FlowRequest,
    step_responses: list,
    on_score: Callable[[ScoreDetail], Awaitable[None]],
    pool,
    job_id: str,
) -> list:
    """
    全 Lead/Support AI が全ステップ回答を採点する（並列）。
    採点対象は SCORER ロール以外の全ステップ。
    """
    # 採点対象のステップ（エラーなし）
    scored_steps = [
        {"ai": r.ai.value, "role": r.role.value, "content": r.content}
        for r in step_responses
        if not r.error and r.role != StepRole.SCORER
    ]

    # 採点するAI（シーンに参加しているAI）
    scoring_ais = list({r.ai for r in step_responses if r.role != StepRole.SCORER})
    scored_ai_names = {r.ai.value for r in step_responses if not r.error}
    ai_map = {ai.value: ai for ai in AIName}

    all_scores: list = []

    async def score_with_ai(scorer_ai: AIName) -> list:
        api_key = _get_api_key(scorer_ai, request)
        model = request.model_overrides.get(scorer_ai.value, "")
        prompt = scoring_prompt(request.question, scored_steps, request.language)
        try:
            content = await _call_ai(
                scorer_ai, prompt, MAX_TOKENS_SCORER, request.language, model, api_key
            )
            parsed = parse_score_response(content)
            if not parsed or "scores" not in parsed:
                logger.warning(f"{scorer_ai.value} の採点JSONパース失敗")
                return []
            results = []
            for s in parsed["scores"]:
                target_name = s.get("target_ai", "")
                # シーンに参加していないAIは除外
                if target_name not in scored_ai_names:
                    continue
                target_ai = ai_map.get(target_name)
                if not target_ai:
                    continue
                is_self = scorer_ai == target_ai
                raw = {k: float(s.get(k, 0)) for k in WEIGHTS}
                wt = calculate_weighted_total(raw, is_self)
                detail = ScoreDetail(
                    scorer_ai=scorer_ai,
                    target_ai=target_ai,
                    is_self=is_self,
                    weighted_total=wt,
                    reason=s.get("reason", ""),
                    **raw,
                )
                results.append(detail)
                await on_score(detail)
                if pool and job_id:
                    await db.save_score(pool, job_id, detail)
            return results
        except Exception as e:
            logger.error(f"{scorer_ai.value} 採点エラー: {e}")
            return []

    tasks = [score_with_ai(ai) for ai in scoring_ais]
    results = await asyncio.gather(*tasks)
    for r in results:
        all_scores.extend(r)

    return all_scores

"""
モックテスト: clients.py の call_* 関数をスタブに差し替えて全フローを検証。
4シーン全てをテスト（APIキー・DB 不要）。
"""
import asyncio
import json
import sys
from unittest import mock

from models import FlowRequest, SceneName, StepRole
from scene_router import get_scene_config
from flow_executor import execute_flow, execute_scorer

# ─────────────────────────────────────────────
# モックスタブ
# ─────────────────────────────────────────────

MOCK_SCORE_JSON = json.dumps({
    "scores": [
        {"target_ai": "Claude",  "accuracy": 8, "evidence": 7, "consistency": 8,
         "coverage": 7, "usefulness": 8, "brevity": 7, "revision_quality": 7, "reason": "Good Claude"},
        {"target_ai": "ChatGPT", "accuracy": 7, "evidence": 8, "consistency": 7,
         "coverage": 8, "usefulness": 7, "brevity": 8, "revision_quality": 7, "reason": "Good ChatGPT"},
        {"target_ai": "Gemini",  "accuracy": 7, "evidence": 7, "consistency": 7,
         "coverage": 7, "usefulness": 7, "brevity": 7, "revision_quality": 7, "reason": "Good Gemini"},
        {"target_ai": "Grok",    "accuracy": 7, "evidence": 7, "consistency": 7,
         "coverage": 7, "usefulness": 7, "brevity": 7, "revision_quality": 7, "reason": "Good Grok"},
    ]
})

MOCK_IMPLEMENTATION = "## 実装手順\n- [ ] ステップ1: 環境構築\n- [ ] ステップ2: コード実装"
MOCK_DECISION       = "## 意思決定分析\n論点: ...\nスティールマン: ...\nリスク: ..."
MOCK_LOGIC          = "## Toulmin分析\n論理の穴: ...\nバイアス: ..."
MOCK_RESEARCH       = "## 調査計画\nEvidence Table: ...\nタイムボックス: ..."
MOCK_SUPPORT        = "## サポート回答\n分析: ..."
MOCK_DEFAULT        = "デフォルトスタブ回答"


def mock_response(prompt: str) -> str:
    """プロンプト内容でスタブを分岐する。"""
    if "accuracy" in prompt:
        return MOCK_SCORE_JSON
    elif "実装" in prompt or "手順" in prompt or "タスク" in prompt or "Implementation" in prompt:
        return MOCK_IMPLEMENTATION
    elif "意思決定" in prompt or "反証" in prompt or "論点" in prompt or "Decision" in prompt:
        return MOCK_DECISION
    elif "論理" in prompt or "バイアス" in prompt or "Toulmin" in prompt or "logical" in prompt.lower():
        return MOCK_LOGIC
    elif "調査" in prompt or "Evidence" in prompt or "リサーチ" in prompt or "Research" in prompt:
        return MOCK_RESEARCH
    elif any(k in prompt for k in ["批評", "欠陥", "改善", "検証", "確信", "不確実", "仮説", "critic", "support"]):
        return MOCK_SUPPORT
    else:
        return MOCK_DEFAULT


async def mock_ai_call(prompt: str, max_tokens: int, language: str, model: str = "", api_key: str = "") -> str:
    return mock_response(prompt)


# ─────────────────────────────────────────────
# テスト実行
# ─────────────────────────────────────────────

async def run_scene(scene_name: str, enable_scorer: bool):
    """1シーンのフロー全体を実行してステップ・スコアを返す。"""
    request = FlowRequest(
        question="テスト質問: この計画の論理的な穴を分析してください",
        scene=SceneName(scene_name),
        enable_scorer=enable_scorer,
        openai_api_key="test-key",
        gemini_api_key="test-key",
        grok_api_key="test-key",
    )
    scene_config = get_scene_config(SceneName(scene_name))

    step_responses = []
    score_details = []

    async def on_step(resp):
        step_responses.append(resp)

    async def on_score(score):
        score_details.append(score)

    with mock.patch("flow_executor.call_claude",  side_effect=mock_ai_call), \
         mock.patch("flow_executor.call_chatgpt", side_effect=mock_ai_call), \
         mock.patch("flow_executor.call_gemini",  side_effect=mock_ai_call), \
         mock.patch("flow_executor.call_grok",    side_effect=mock_ai_call):

        await execute_flow(request, scene_config, on_step, None, "")

        if enable_scorer:
            await execute_scorer(request, step_responses, on_score, None, "")

    return step_responses, score_details


async def main():
    # シーンごとの期待値: (scene_name, enable_scorer, expected_steps)
    test_cases = [
        ("implementation", False, 3),
        ("decision",       True,  3),
        ("logic_check",    True,  3),
        ("research",       False, 3),
    ]

    all_passed = True
    print("=" * 60)

    for scene_name, enable_scorer, expected_steps in test_cases:
        steps, scores = await run_scene(scene_name, enable_scorer)

        errors   = [s for s in steps if s.error]
        no_content = [s for s in steps if not s.content and not s.error]

        ok_steps    = len(steps) == expected_steps
        ok_errors   = len(errors) == 0
        ok_content  = len(no_content) == 0
        ok_scorer   = (len(scores) > 0) == enable_scorer

        passed = ok_steps and ok_errors and ok_content and ok_scorer
        status = "✅" if passed else "❌"
        all_passed = all_passed and passed

        scorer_info = f"スコア={len(scores)}件" if enable_scorer else "Scorer=OFF"
        print(f"{status} [{scene_name}]  ステップ={len(steps)}/{expected_steps}  {scorer_info}")

        if not ok_steps:
            print(f"   ⚠ ステップ数不一致: 期待={expected_steps}, 実際={len(steps)}")
        if errors:
            for e in errors:
                print(f"   ⚠ エラー: step{e.step_index} {e.ai.value}: {e.error}")
        if no_content:
            print(f"   ⚠ content なし: {[f'step{s.step_index}' for s in no_content]}")
        if not ok_scorer and enable_scorer:
            print(f"   ⚠ スコア件数が 0 (scorer=ON なのに採点なし)")

    print("=" * 60)
    if all_passed:
        print("✅ 全テスト通過")
    else:
        print("❌ テスト失敗")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

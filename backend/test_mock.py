"""
モックテスト: _call_ai をスタブに差し替えて全フローを検証。
4AI・2ラウンド・改訂あり → 期待レスポンス数: 36件
  Phase 0   : 4  (initial × 4)
  Phase 1   : 12 (evaluation: 4AI × 3対象)
  Phase 2   : 12 (evaluation: 4AI × 3対象)
  Phase rev : 4  (revision × 4)
  Phase score: 4 (scoring × 4)
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from unittest.mock import patch
from models import AIName, ResponseType, DebateConfig, DebateResponse


def _make_score_json(ai_names: list[str]) -> str:
    """スコアJSONスタブを生成。"""
    scores = [
        {
            "target_ai": name,
            "accuracy": 8.0,
            "evidence": 7.0,
            "consistency": 7.5,
            "coverage": 8.0,
            "usefulness": 7.5,
            "brevity": 7.0,
            "revision_quality": 7.0,
            "reason": f"{name}のテスト採点理由",
        }
        for name in ai_names
    ]
    return json.dumps({"scores": scores, "overall_analysis": "テスト全体分析"})


async def _mock_call_ai(ai, prompt, config, max_tokens, semaphore, model_override=""):
    """
    スタブ判定:
    - "accuracy" が含まれる → スコア JSON
    - "改訂" または "revise" が含まれる → 改訂スタブ
    - それ以外 → 初回/評価スタブ
    """
    ai_names = [a.value for a in config.enabled_ais]
    if "accuracy" in prompt:
        return _make_score_json(ai_names)
    elif "改訂" in prompt or "revise" in prompt.lower():
        return "【改訂点】\n- テスト改訂点\n\n改訂済み回答テスト"
    else:
        return f"{ai.value} のテスト回答"


async def run_test():
    config = DebateConfig(
        question="テスト質問",
        rounds=2,
        enabled_ais=list(AIName),
        enable_revision=True,
    )

    responses: list[DebateResponse] = []

    async def on_response(resp: DebateResponse):
        responses.append(resp)

    # debate._call_ai をモックに差し替え
    with patch("debate._call_ai", side_effect=_mock_call_ai):
        from debate import run_debate
        await run_debate(config, on_response)

    # -------- アサート --------
    total = len(responses)
    errors = [r for r in responses if r.error]
    revision_resps = [r for r in responses if r.response_type == ResponseType.REVISION]
    scoring_resps = [r for r in responses if r.response_type == ResponseType.SCORING]

    print(f"\n実際レスポンス数: {total}")
    print(f"  initial  : {sum(1 for r in responses if r.response_type == ResponseType.INITIAL)}")
    print(f"  evaluation: {sum(1 for r in responses if r.response_type == ResponseType.EVALUATION)}")
    print(f"  revision : {len(revision_resps)}")
    print(f"  scoring  : {len(scoring_resps)}")
    print(f"  errors   : {len(errors)}")

    assert total == 36, f"❌ レスポンス数: 期待 36, 実際 {total}"
    assert len(errors) == 0, f"❌ エラーあり: {[r.error for r in errors]}"
    assert len(revision_resps) == 4, f"❌ revision 数: 期待 4, 実際 {len(revision_resps)}"
    assert all(r.revision_of is not None for r in revision_resps), \
        "❌ revision_of が未設定の revision レスポンスがあります"
    assert len(scoring_resps) == 4, f"❌ scoring 数: 期待 4, 実際 {len(scoring_resps)}"

    print("\n✅ 全テスト通過")


if __name__ == "__main__":
    asyncio.run(run_test())

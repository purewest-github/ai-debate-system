"""
実機動作確認スクリプト
.env から APIキーを読み込み、サーバーに対して実際にリクエストを送る。
"""
import asyncio
import json
import os
import sys
import time
import httpx
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GROK_KEY   = os.environ.get("GROK_API_KEY", "") or os.environ.get("XAI_API_KEY", "")
API_BASE   = "http://localhost:8000"

SCENE_LABELS = {
    "implementation": "実装・タスク分解",
    "decision":       "意思決定支援",
    "logic_check":    "論理チェック",
    "research":       "情報収集・リサーチ設計",
}


# ─────────────────────────────────────────────
# 1. シーン自動判定テスト
# ─────────────────────────────────────────────

DETECT_CASES = [
    ("Pythonでバッチ処理を実装する手順を教えて",                       "implementation"),
    ("転職すべきかどうか判断したい",                                   "decision"),
    ("この文章の論理的な欠陥を指摘して：AIは必ず人間より賢くなる",     "logic_check"),
    ("競合他社の技術動向を調べる方法を設計したい",                     "research"),
]

async def run_detect_tests():
    print("\n" + "=" * 70)
    print("【1. シーン自動判定テスト】")
    print("=" * 70)
    correct = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for question, expected in DETECT_CASES:
            resp = await client.post(f"{API_BASE}/api/scene/detect", json={
                "question": question,
                "gemini_api_key": GEMINI_KEY,
            })
            if resp.status_code != 200:
                print(f"  ❌ HTTPエラー {resp.status_code}: {question[:30]}")
                continue
            data = resp.json()
            scene      = data.get("scene", "?")
            confidence = data.get("confidence", 0)
            reason     = data.get("reason", "")
            ok = scene == expected
            if ok: correct += 1
            mark = "✅" if ok else "❌"
            print(f"\n  {mark} 質問: {question[:40]}")
            print(f"     期待: {expected}  →  判定: {scene}  (確信度: {confidence:.0%})")
            print(f"     理由: {reason[:80]}")
    print(f"\n  判定精度: {correct}/{len(DETECT_CASES)} 正解")
    return correct


# ─────────────────────────────────────────────
# 2. フルフロー実機テスト
# ─────────────────────────────────────────────

FLOW_CASES = [
    ("implementation", "FastAPIでJWT認証を実装する手順を教えて"),
    ("decision",       "個人開発のプロダクトをOSSで公開すべきか判断したい"),
    ("logic_check",    "マイクロサービスは常にモノリスより優れている"),
    ("research",       "LLMを使ったコード生成ツールの最新動向を調べたい"),
]

ROLE_LABELS = {
    "lead":               "🎯 Lead",
    "support_critic":     "🔍 批評",
    "support_organizer":  "📋 整理",
    "support_validator":  "📊 検証",
    "support_executor":   "⚡ 実行",
    "support_rewriter":   "✏️ 言い直し",
    "support_confidence": "📈 信頼度",
    "support_uncertainty":"⚠️ 不確実性",
    "support_hypothesis": "🧪 仮説検証",
    "scorer":             "🏆 採点",
}

async def run_flow(scene: str, question: str):
    """SSE ストリームを受信してステップ一覧を返す。"""
    body = {
        "question": question,
        "scene": scene,
        "enable_scorer": False,
        "openai_api_key": OPENAI_KEY,
        "gemini_api_key": GEMINI_KEY,
        "grok_api_key":   GROK_KEY,
        "language": "ja",
        "model_overrides": {},
    }
    steps = []
    errors = []
    t0 = time.time()

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", f"{API_BASE}/api/flow/stream",
                                  json=body, headers={"Accept": "text/event-stream"}) as resp:
            if resp.status_code != 200:
                return steps, errors, time.time() - t0

            buf = ""
            async for chunk in resp.aiter_text():
                buf += chunk
                while "\n\n" in buf:
                    event, buf = buf.split("\n\n", 1)
                    for line in event.splitlines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if not raw or raw.startswith(":"):
                            continue
                        try:
                            ev = json.loads(raw)
                            if ev.get("type") == "step_complete":
                                d = ev["data"]
                                steps.append(d)
                                if d.get("error"):
                                    errors.append(d)
                            elif ev.get("type") == "complete":
                                return steps, errors, time.time() - t0
                        except json.JSONDecodeError:
                            pass
    return steps, errors, time.time() - t0


async def run_flow_tests():
    print("\n" + "=" * 70)
    print("【2. フルフロー実機テスト】")
    print("=" * 70)
    success_count = 0
    total_errors = 0

    for scene, question in FLOW_CASES:
        print(f"\n  ▶ [{SCENE_LABELS[scene]}]  質問: {question[:50]}")
        steps, errors, elapsed = await run_flow(scene, question)
        total_errors += len(errors)

        if len(steps) >= 3 and len(errors) == 0:
            success_count += 1
            print(f"  ✅ 完了 ({elapsed:.1f}秒 / {len(steps)}ステップ / エラー {len(errors)}件)")
        else:
            print(f"  ❌ 失敗 ({elapsed:.1f}秒 / {len(steps)}ステップ / エラー {len(errors)}件)")

        for s in steps:
            label = ROLE_LABELS.get(s.get("role",""), s.get("role",""))
            ai    = s.get("ai","?")
            cont  = s.get("content","")
            err   = s.get("error")
            # 先頭100文字だけ要約表示
            summary = err if err else (cont[:120].replace("\n","  ").strip() + ("…" if len(cont) > 120 else ""))
            status = "⚠" if err else "  "
            print(f"  {status}  Step{s.get('step_index','-')} {ai} ({label}): {summary}")

    print(f"\n  フロー成功: {success_count}/{len(FLOW_CASES)} シーン")
    print(f"  合計エラー: {total_errors} 件")
    return success_count, total_errors


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

async def main():
    print("\n🔍 AI Scene Router 実機動作確認")
    print(f"   GEMINI_KEY:  {'✅ 設定済' if GEMINI_KEY else '❌ 未設定'}")
    print(f"   OPENAI_KEY:  {'✅ 設定済' if OPENAI_KEY else '❌ 未設定'}")
    print(f"   GROK_KEY:    {'✅ 設定済' if GROK_KEY else '❌ 未設定'}")

    detect_correct = await run_detect_tests()
    flow_success, total_errors = await run_flow_tests()

    print("\n" + "=" * 70)
    print("【3. 結果レポート】")
    print("=" * 70)
    print(f"  シーン判定精度: {detect_correct}/4 正解")
    print(f"  フロー完了:     {flow_success}/4 シーン成功")
    print(f"  エラー件数:     {total_errors} 件")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

"""
シーン自動判定: Gemini-flash を使って質問のシーンを分類する。
"""
import json
import logging

from models import SceneName, DetectResponse
from prompts import scene_detection_prompt
from clients import call_gemini

logger = logging.getLogger(__name__)

# 判定に使用するモデル（固定）
DETECT_MODEL = "gemini-2.0-flash"


async def detect_scene(question: str, gemini_api_key: str) -> DetectResponse:
    """
    Gemini-flash でシーンを自動判定する。
    - JSON パース失敗時は SceneName.DECISION をデフォルトとして返す
    - confidence < 0.5 の場合は reason に警告を付記
    """
    prompt = scene_detection_prompt(question)
    try:
        content = await call_gemini(
            prompt=prompt,
            max_tokens=256,
            language="en",
            model=DETECT_MODEL,
            api_key=gemini_api_key,
        )

        # JSON パース
        cleaned = content.strip()
        # コードフェンス除去
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        parsed = json.loads(cleaned)
        scene_str = parsed.get("scene", "decision")
        confidence = float(parsed.get("confidence", 0.5))
        reason = parsed.get("reason", "")

        # 有効なシーン名に変換
        try:
            scene = SceneName(scene_str)
        except ValueError:
            logger.warning(f"未知のシーン '{scene_str}'、decision にフォールバック")
            scene = SceneName.DECISION

        # 低確信度に警告を付記
        if confidence < 0.5:
            reason = f"[自動判定の信頼度が低いため確認推奨] {reason}"

        return DetectResponse(scene=scene, confidence=confidence, reason=reason)

    except Exception as e:
        logger.warning(f"シーン判定失敗: {e}。decision にフォールバック")
        return DetectResponse(
            scene=SceneName.DECISION,
            confidence=0.0,
            reason=f"自動判定に失敗しました（{e}）。手動でシーンを選択してください。",
        )

import json
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 重み合計 = 1.0
WEIGHTS = {
    "accuracy": 0.30,
    "evidence": 0.20,
    "consistency": 0.15,
    "coverage": 0.15,
    "usefulness": 0.12,
    "brevity": 0.05,
    "revision_quality": 0.03,
}


def parse_score_response(content: str) -> Optional[dict]:
    """コードフェンスを除去してJSONパース。失敗時はNone。"""
    # コードフェンス除去
    cleaned = re.sub(r"```(?:json)?\n?", "", content).strip()
    cleaned = cleaned.rstrip("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # JSON部分を抽出して再試行
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                # 末尾が切れている場合、最後の完全なオブジェクトまでを抽出して再パース
                partial = match.group()
                # 末尾の不完全なエントリを除去: 最後の '}' で終わる位置まで切り詰める
                last_brace = partial.rfind("}")
                if last_brace != -1:
                    truncated = partial[: last_brace + 1]
                    # 開き括弧と閉じ括弧の数を合わせて補完
                    open_count = truncated.count("{") - truncated.count("}")
                    truncated += "}" * open_count
                    try:
                        return json.loads(truncated)
                    except json.JSONDecodeError:
                        pass
    logger.warning("スコアJSONのパースに失敗しました")
    return None


def calculate_weighted_total(raw: dict, is_self: bool) -> float:
    """各軸スコア × 重み × 10 で 0〜100 換算。is_self=True のとき 0.5 倍。"""
    total = sum(raw.get(axis, 0) * weight * 10 for axis, weight in WEIGHTS.items())
    if is_self:
        total *= 0.5
    return round(total, 2)


def aggregate_final_scores(score_details: list) -> dict:
    """AI 別に weighted_total の平均を計算してランク付け。"""
    from collections import defaultdict
    totals: dict = defaultdict(list)
    for s in score_details:
        totals[s.target_ai.value].append(s.weighted_total)

    aggregated = {}
    for ai_name, scores in totals.items():
        avg = sum(scores) / len(scores) if scores else 0
        aggregated[ai_name] = round(avg, 2)

    # ランク付き
    ranked = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)
    for rank, (ai_name, score) in enumerate(ranked, 1):
        aggregated[ai_name] = {"score": score, "rank": rank}

    return aggregated


def build_ranking(aggregated: dict) -> list:
    """スコア降順の AI 名リスト。"""
    items = [(ai_name, data["score"]) for ai_name, data in aggregated.items()]
    return [ai for ai, _ in sorted(items, key=lambda x: x[1], reverse=True)]

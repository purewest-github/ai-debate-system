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
    """
    採点者ごとに z-score 正規化してから AI 別平均を計算してランク付け。
    採点基準が甘い/辛い採点者の影響を補正する。
    """
    import math
    from collections import defaultdict

    # 採点者ごとに weighted_total を収集
    by_scorer: dict = defaultdict(list)
    for s in score_details:
        by_scorer[s.scorer_ai.value].append(s.weighted_total)

    # 採点者ごとの平均・標準偏差を計算
    scorer_stats: dict = {}
    for scorer, scores in by_scorer.items():
        mean = sum(scores) / len(scores)
        variance = sum((x - mean) ** 2 for x in scores) / len(scores)
        std = math.sqrt(variance)
        scorer_stats[scorer] = {"mean": mean, "std": std}

    # z-score 正規化した値を AI 別に収集
    normalized: dict = defaultdict(list)
    for s in score_details:
        stats = scorer_stats[s.scorer_ai.value]
        if stats["std"] > 0:
            # z-score を 0〜100 スケールに変換（平均50、標準偏差10）
            z = (s.weighted_total - stats["mean"]) / stats["std"]
            norm = 50.0 + z * 10.0
        else:
            # 全スコアが同値の場合は元の値をそのまま使用
            norm = s.weighted_total
        normalized[s.target_ai.value].append(norm)

    aggregated = {}
    for ai_name, scores in normalized.items():
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

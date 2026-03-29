from typing import List, Dict


def initial_prompt(question: str, language: str) -> str:
    """初回回答プロンプト。"""
    if language == "ja":
        return f"""以下の質問に対して、包括的で詳細な回答を提供してください。

質問: {question}

回答には以下を含めてください：
- 主要な論点と観点
- 具体的な根拠や証拠
- 実用的な洞察や提言
- 論理的な結論

できるだけ詳しく、論理的かつ体系的に回答してください。"""
    else:
        return f"""Please provide a comprehensive and detailed answer to the following question.

Question: {question}

Your answer should include:
- Key arguments and perspectives
- Specific evidence and reasoning
- Practical insights and recommendations
- Logical conclusions

Please answer as thoroughly and systematically as possible."""


def evaluation_prompt(
    question: str,
    target_ai: str,
    prev_responses: List[Dict],
    round_num: int,
    language: str,
) -> str:
    """他 AI の回答を評価するプロンプト。"""
    target_content = next(
        (r["content"] for r in prev_responses if r["ai"] == target_ai), "（回答なし）"
    )
    other_responses = "\n\n".join(
        f"【{r['ai']}の回答】\n{r['content']}"
        for r in prev_responses
        if r["ai"] != target_ai
    )

    if language == "ja":
        return f"""以下の「{target_ai}」の回答を批評的に評価してください。

元の質問: {question}

評価ラウンド: {round_num}

【{target_ai}の回答】
{target_content}

【参考：他のAIの回答】
{other_responses}

以下の6つの観点から評価してください：
1. 正確性：情報は正確で信頼できるか
2. 完全性：質問に対して網羅的に答えているか
3. 論理性：論拠は一貫して論理的か
4. 洞察力：独自の洞察や深い分析があるか
5. 根拠：主張を支える証拠が十分か
6. 改善提案：より良い回答にするための具体的な改善点

具体的で建設的な評価を提供し、改善点を明確に指摘してください。"""
    else:
        return f"""Please critically evaluate the following response from "{target_ai}".

Original question: {question}

Evaluation round: {round_num}

[{target_ai}'s response]
{target_content}

[Reference: Other AI responses]
{other_responses}

Evaluate from the following 6 perspectives:
1. Accuracy: Is the information accurate and reliable?
2. Completeness: Does it comprehensively address the question?
3. Logic: Is the reasoning consistent and logical?
4. Insight: Are there unique insights or deep analysis?
5. Evidence: Is there sufficient evidence to support claims?
6. Improvement suggestions: What specific improvements would make this better?

Provide specific and constructive evaluation with clear improvement points."""


def revision_prompt(
    question: str,
    my_ai: str,
    my_initial_content: str,
    critiques: List[Dict],
    language: str,
) -> str:
    """他 AI からの批評を踏まえた自己改訂プロンプト。"""
    critiques_text = "\n\n".join(
        f"【{c['ai']}からの批評】\n{c['content']}" for c in critiques
    )

    if language == "ja":
        return f"""あなたは{my_ai}です。以下の質問に対するあなたの初回回答を、他のAIからの批評を踏まえて改訂してください。

元の質問: {question}

【あなたの初回回答】
{my_initial_content}

【他のAIからの批評】
{critiques_text}

改訂版を作成する際の指示：
1. 冒頭に【改訂点】セクションを設け、変更箇所と理由を箇条書きで明示してください
2. その後に改訂済みの完全な回答を提供してください
3. 批評の中で妥当な指摘は積極的に取り入れてください
4. 改訂が不要と判断した場合は「【改訂不要】理由: ...」と記述し、理由を明記してください

批評を真剣に受け止め、より質の高い回答を提供してください。"""
    else:
        return f"""You are {my_ai}. Please revise your initial response to the following question based on critiques from other AIs.

Original question: {question}

[Your initial response]
{my_initial_content}

[Critiques from other AIs]
{critiques_text}

Instructions for creating the revision:
1. Begin with a [Revision Points] section listing changes and reasons as bullet points
2. Then provide the complete revised response
3. Incorporate valid criticisms proactively
4. If no revision is needed, write "[No Revision Needed] Reason: ..." with explanation

Take the critiques seriously and provide a higher quality response."""


def scoring_prompt_v2(
    question: str,
    all_responses: List[Dict],
    ai_names: List[str],
    language: str,
) -> str:
    """全回答を全文渡して7軸 JSON 採点を求めるプロンプト。"""
    responses_text = "\n\n".join(
        f"【{r['ai']} - {r['phase']}】\n{r['content']}" for r in all_responses
    )
    ai_list = " / ".join(ai_names)

    if language == "ja":
        return f"""以下の質問に対する複数のAIの回答を7つの軸で採点してください。

元の質問: {question}

採点対象のAI: {ai_list}

===== 全回答（改訂版を含む） =====
{responses_text}
===================================

採点指示：
- 各AIについて以下の7軸でスコアを付けてください（各軸 0〜10 の数値）
- あなた自身（採点者）のスコアも必ず含めてください（システム側で 0.5 倍ペナルティを適用します）
- エラーが発生したAIは全軸 0 点としてください
- 結果は以下のJSON形式のみで出力してください（コードフェンスなし、余計な説明文なし）

採点軸：
- accuracy（正確性）：情報の正確さと信頼性
- evidence（根拠）：主張を支える証拠の質と量
- consistency（一貫性）：論理の一貫性と矛盾のなさ
- coverage（網羅性）：質問に対する回答の網羅度
- usefulness（実用性）：実際の役立ちやすさ
- brevity（簡潔さ）：冗長さを避けた簡潔な表現
- revision_quality（改訂品質）：批評を受けた改善の質（改訂なしの場合は初回回答の質で評価）

出力形式（必ずこの形式のみ）:
{{"scores": [{{"target_ai": "AI名", "accuracy": 数値, "evidence": 数値, "consistency": 数値, "coverage": 数値, "usefulness": 数値, "brevity": 数値, "revision_quality": 数値, "reason": "採点理由"}}], "overall_analysis": "全体分析"}}"""
    else:
        return f"""Please score the responses from multiple AIs to the following question on 7 axes.

Original question: {question}

AIs to score: {ai_list}

===== All responses (including revisions) =====
{responses_text}
===============================================

Scoring instructions:
- Score each AI on the following 7 axes (0-10 per axis)
- You MUST include a score for yourself (the system applies a 0.5x penalty to self-scores)
- AIs that encountered errors should receive 0 on all axes
- Output ONLY the following JSON format (no code fences, no extra text)

Scoring axes:
- accuracy: Information accuracy and reliability
- evidence: Quality and quantity of evidence supporting claims
- consistency: Logical consistency and lack of contradictions
- coverage: Comprehensiveness of response
- usefulness: Practical utility
- brevity: Concise expression avoiding redundancy
- revision_quality: Quality of improvement from critiques (for no revision, evaluate initial response quality)

Output format (ONLY this format):
{{"scores": [{{"target_ai": "AI name", "accuracy": number, "evidence": number, "consistency": number, "coverage": number, "usefulness": number, "brevity": number, "revision_quality": number, "reason": "scoring reason"}}], "overall_analysis": "overall analysis"}}"""

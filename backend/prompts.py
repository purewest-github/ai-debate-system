"""
AI Scene Router — プロンプト生成関数
各関数は language: str ("ja"/"en") を受け取り出力言語を切り替える。
"""


# ─────────────────────────────────────────────
# Lead プロンプト
# ─────────────────────────────────────────────

def lead_implementation(question: str, language: str) -> str:
    """ChatGPT lead: 実装・タスク分解"""
    if language == "en":
        return f"""You are an expert software engineer specializing in breaking down complex tasks.

Question / Task:
{question}

Provide a complete step-by-step implementation plan:

## Prerequisites
- Required tools and versions
- Environment setup
- Estimated total time

## Implementation Steps
For each step:
- [ ] Step N: Clear action description
  - Details and commands if applicable
  - Estimated time
  - Potential pitfalls

Be thorough and practical."""
    return f"""あなたは複雑なタスクの分解を専門とするソフトウェアエンジニアです。

質問・タスク:
{question}

以下の構成で完全なステップバイステップの実装手順を提供してください：

## 前提条件
- 必要なツールとバージョン
- 環境構築の要件
- 合計所要時間の目安

## 実装手順
各ステップに以下を含めること：
- [ ] ステップ N: 具体的なアクション
  - 詳細・コマンド（必要な場合）
  - 所要時間の目安
  - 注意点・落とし穴

実践的で網羅的に記述してください。"""


def lead_decision(question: str, language: str) -> str:
    """Claude lead: 意思決定支援"""
    if language == "en":
        return f"""You are a strategic advisor using structured reasoning frameworks.

Decision Question:
{question}

Analyze using this framework:

## Core Argument Structure
- Central claim and supporting premises

## Steelman (Strongest Counterargument)
- Most compelling case AGAINST the primary recommendation

## Premises & Assumptions
- Hidden assumptions (mark which are testable)

## Risks & Mitigations
- Key risks ranked by severity × probability

## Alternatives
- At least 2 alternative approaches with trade-offs

## Popper Falsifiability Check
- What evidence would prove this decision WRONG?"""
    return f"""あなたは構造化推論フレームワークを用いる戦略アドバイザーです。

意思決定の質問:
{question}

以下のフレームワークで分析してください：

## 論点の骨格
- 中心的な主張と根拠となる前提

## スティールマン（最強の反論）
- 主要推奨に対する最も説得力のある反論

## 前提・仮定
- 隠れた前提を列挙（テスト可能なものにはマーク）

## リスクと対策
- 重大度×確率でランク付けした主要リスク

## 代替案
- 少なくとも2つの代替アプローチとトレードオフ

## ポパーの反証可能性チェック
- この意思決定が「誤り」と判明する証拠は何か？"""


def lead_logic_check(text: str, language: str) -> str:
    """Claude lead: 論理チェック"""
    if language == "en":
        return f"""You are a critical thinking expert specializing in logical analysis.

Text to analyze:
{text}

Perform rigorous logical analysis using the Toulmin model:

## Toulmin Structure
- Claim / Data / Warrant / Backing / Qualifier / Rebuttal

## Logical Fallacies & Gaps
- Each fallacy with type (ad hominem, strawman, etc.)
- Hidden premises
- Weakest points

## Cognitive Biases Detected
- Classify each bias type

## Specific Vulnerabilities
- Most effective counterattacks and why they succeed"""
    return f"""あなたは論理分析を専門とする批判的思考の専門家です。

分析対象テキスト:
{text}

Toulminモデルを用いて厳密な論理分析を実施してください：

## Toulmin構造
- 主張 / データ / 論拠 / 裏付け / 限定詞 / 反駁

## 論理の穴・誤謬
- 各誤謬を種類（ad hominem、わら人形論法等）とともに列挙
- 隠れた前提
- 最も弱い箇所

## 検出されたバイアス
- 各バイアスの種類を分類

## 具体的な脆弱箇所
- 最も有効な反論とその理由"""


def lead_research(question: str, language: str) -> str:
    """Grok lead: 情報収集・リサーチ設計"""
    if language == "en":
        return f"""You are an expert research strategist.

Research Question:
{question}

Design a complete investigation plan:

## Research Hypotheses
- Primary hypothesis
- Alternative hypotheses

## Evidence Table
| Source Type | Specific Sources | Reliability (H/M/L) | Priority | Time |
|---|---|---|---|---|

## Timebox Research Steps
### Phase 1 (Quick: 30 min)
### Phase 2 (Deep: 2-4 hours)
### Phase 3 (Synthesis: 1-2 hours)

## Success Criteria
- What constitutes sufficient evidence?"""
    return f"""あなたは包括的な調査計画を設計するリサーチ戦略の専門家です。

調査質問:
{question}

完全な調査計画を設計してください：

## 調査仮説
- 主要仮説
- 代替仮説

## Evidence Table（情報源テーブル）
| 情報源種別 | 具体的な情報源 | 信頼度(高/中/低) | 優先度 | 所要時間 |
|---|---|---|---|---|

## タイムボックス別調査ステップ
### フェーズ1（クイックスキャン: 30分）
### フェーズ2（深掘り: 2〜4時間）
### フェーズ3（統合: 1〜2時間）

## 成功基準
- 質問に回答するのに十分な証拠とは何か？"""


# ─────────────────────────────────────────────
# Support プロンプト
# ─────────────────────────────────────────────

def support_critic(question: str, lead_output: str, language: str) -> str:
    """Claude support: 抜け漏れ・前提の見落とし・反証を指摘"""
    if language == "en":
        return f"""You are a rigorous critic finding specific flaws.

Original Question:
{question}

Analysis to Critique:
{lead_output}

## Missing Elements
- Important aspects not addressed
- Ignored perspectives

## Flawed Assumptions
- Each questionable assumption with reasoning

## Counterexamples
- Concrete cases contradicting the analysis

## Logical Weaknesses
- Specific errors with quotes

## Improvement Suggestions
- Actionable ways to strengthen the analysis"""
    return f"""あなたは具体的な欠陥を見つける厳格な批評家です。

元の質問:
{question}

批評対象の分析:
{lead_output}

## 抜け漏れ
- 対処されなかった重要な側面
- 無視されたステークホルダーや視点

## 問題のある前提
- 各疑問前提を根拠とともに列挙

## 反証例
- 分析に矛盾する具体的なケース

## 論理的弱点
- 引用を伴う具体的な推論エラー

## 改善提案
- 分析を強化するための実行可能な方法"""


def support_organizer(question: str, lead_output: str, critic_output: str, language: str) -> str:
    """Grok support: 記録体系化"""
    if language == "en":
        return f"""You are an expert in organizing information for action.

Original Question:
{question}

Lead Analysis:
{lead_output}

Critic's Feedback:
{critic_output}

Synthesize into a structured record:

## Revised Evidence Table
| Finding | Source | Reliability | Status |
|---|---|---|---|

## Updated Timebox Plan
### Immediate (Today) / Short-term (This Week) / Medium-term (This Month)

## Open Questions
## Decision Log"""
    return f"""あなたは情報を実行のために整理する専門家です。

元の質問:
{question}

リード分析:
{lead_output}

批評者のフィードバック:
{critic_output}

両方を構造化された実行可能な記録に統合してください：

## 更新されたEvidence Table
| 発見事項 | 情報源 | 信頼度 | ステータス |
|---|---|---|---|

## 更新されたタイムボックスプラン
### 即時アクション（本日中）/ 短期（今週中）/ 中期（今月中）

## 未解決の問い
## 決定ログ"""


def support_validator(question: str, lead_output: str, language: str) -> str:
    """Gemini support: 確信度数値化"""
    if language == "en":
        return f"""You are a Bayesian reasoning expert assessing confidence.

Original Question:
{question}

Analysis to Validate:
{lead_output}

For each major claim:
- **Claim**: [quote]
- **Prior**: P = X.XX
- **Evidence**: [Strong/Moderate/Weak]
- **Posterior**: P = X.XX
- **Key uncertainty**: Main factor

## Overall Assessment
- Weighted confidence: X.XX
- Most/least reliable elements
- Critical evidence still needed"""
    return f"""あなたは確信度を評価するベイズ推論の専門家です。

元の質問:
{question}

検証対象の分析:
{lead_output}

各主要主張について：
- **主張**: [引用]
- **事前確率**: P = X.XX
- **証拠の強さ**: [強/中/弱]
- **事後確率**: P = X.XX
- **主要な不確実性**: 確信度を下げる主な要因

## 総合評価
- 加重平均確信度: X.XX
- 最も信頼できる/低い要素
- まだ必要な重要な証拠"""


def support_executor(question: str, lead_output: str, language: str) -> str:
    """ChatGPT support: 実務アクションプラン化"""
    if language == "en":
        return f"""You are an expert converting analysis into executable actions.

Original Question:
{question}

Analysis to Operationalize:
{lead_output}

## Immediate Actions (Next 24 Hours)
- [ ] Action: [task] → Owner: [role] → Time: [X hours]

## This Week's Sprint
- [ ] [Day 1-2]: ...

## Success Metrics (measurable KPIs)
## Resources Required
## Risk Mitigation"""
    return f"""あなたは分析を即座に実行可能なアクションに変換する専門家です。

元の質問:
{question}

実務化対象の分析:
{lead_output}

## 即時アクション（今後24時間）
- [ ] アクション: [タスク] → 担当: [役割] → 時間: [X時間]

## 今週のスプリント
- [ ] [1〜2日目]: ...

## 成功指標（測定可能なKPI）
## 必要リソース
## リスク軽減"""


def support_rewriter(original_text: str, critic_output: str, language: str) -> str:
    """ChatGPT support: 論理チェック後の言い直し"""
    if language == "en":
        return f"""You are an expert editor improving arguments based on critique.

Original Text:
{original_text}

Logical Critique:
{critic_output}

## Revised Version
[Improved text addressing all major criticisms]

## Changes Made
- **Original**: / **Revised**: / **Reason**:

## Remaining Limitations"""
    return f"""あなたは論理的な批評に基づいて論証を改善するエキスパートエディターです。

元のテキスト:
{original_text}

論理的な批評:
{critic_output}

## 改訂版
[主要な批評すべてに対処した改善されたテキスト]

## 変更点
- **変更前**: / **変更後**: / **理由**:

## 残存する制限"""


def support_confidence(
    original_text: str, critic_output: str, rewritten_output: str, language: str
) -> str:
    """Gemini support: 修正後の論理強度スコアリング"""
    if language == "en":
        return f"""You are a logic quality assessor measuring improvement from revision.

Original Text:
{original_text}

Critique:
{critic_output}

Revised Version:
{rewritten_output}

## Logic Strength Comparison
| Dimension | Original (0-10) | Revised (0-10) | Delta |
|---|---|---|---|
| Logical coherence | | | |
| Evidence strength | | | |
| Assumption clarity | | | |
| Counterargument coverage | | | |

## Confidence Scores
- Original: P = X.XX / Revised: P = X.XX / Delta: +X.XX

## Key Improvements / Remaining Vulnerabilities"""
    return f"""あなたは改訂による論理強度の改善を測定する論理品質評価者です。

元のテキスト:
{original_text}

批評:
{critic_output}

改訂版:
{rewritten_output}

## 論理強度比較
| 次元 | 元版 (0-10) | 改訂版 (0-10) | 改善度 |
|---|---|---|---|
| 論理的一貫性 | | | |
| 証拠の強さ | | | |
| 前提の明確さ | | | |
| 反論への対応 | | | |

## 確信度スコア
- 元版: P = X.XX / 改訂版: P = X.XX / 改善デルタ: +X.XX

## 達成された主要改善点 / 残存する脆弱性"""


def support_uncertainty(research_plan: str, language: str) -> str:
    """Gemini support: 調査計画の不確実性マーキング"""
    if language == "en":
        return f"""You are a risk analyst assessing research uncertainty.

Research Plan:
{research_plan}

For each element:
- **Element**: / **Confidence**: X.XX / **Risk Type**: / **Impact**: / **Mitigation**:

## High-Risk Areas (confidence < 0.5)
## Overall Plan Reliability
- Weighted confidence: X.XX
- Recommended adjustments"""
    return f"""あなたはリサーチの不確実性評価を専門とするリスクアナリストです。

調査計画:
{research_plan}

各要素に不確実性スコアを付与してください：
- **要素**: / **確信度**: X.XX / **リスク種別**: / **影響**: / **軽減策**:

## 高リスク領域（確信度 < 0.5）
## 計画全体の信頼性
- 加重確信度スコア: X.XX
- 推奨調整事項"""


def support_hypothesis(research_plan: str, language: str) -> str:
    """Claude support: 調査仮説の論理的妥当性検証"""
    if language == "en":
        return f"""You are a research methodology expert validating hypotheses.

Research Plan:
{research_plan}

For each hypothesis:
- **Hypothesis**: / **Falsifiable?**: / **Testable?**: / **Assumptions**: / **Verdict**: [Valid/Partially/Invalid]

## Logical Relationships between hypotheses
## Recommended Refinements
## Missing Hypotheses
(Apply strict Popperian standards)"""
    return f"""あなたは仮説の論理的妥当性を検証するリサーチ方法論の専門家です。

調査計画:
{research_plan}

各仮説について：
- **仮説**: / **反証可能か**: / **検証可能か**: / **必要な前提**: / **判定**: [妥当/部分的/妥当でない]

## 仮説間の論理的関係
## 推奨される改善
## 欠けている仮説
（厳格なポパー基準を適用すること）"""


# ─────────────────────────────────────────────
# Scorer プロンプト
# ─────────────────────────────────────────────

def scoring_prompt(question: str, step_responses: list, language: str) -> str:
    """全ステップの回答を全文含む採点プロンプト"""
    responses_text = ""
    for r in step_responses:
        responses_text += f"\n\n=== {r['ai']} ({r['role']}) ===\n{r['content']}"

    if language == "en":
        return f"""You are an objective evaluator scoring AI responses on 7 axes.

Original Question:
{question}

All Responses:
{responses_text}

Score EVERY AI above on all 7 axes (0-10). Include self-scoring (system applies 0.5x penalty).
If an AI had an error, score all axes as 0.

Return ONLY valid JSON (no code fences):
{{
  "scores": [
    {{
      "target_ai": "Claude",
      "accuracy": 8.5,
      "evidence": 7.0,
      "consistency": 8.0,
      "coverage": 7.5,
      "usefulness": 8.0,
      "brevity": 6.5,
      "revision_quality": 7.0,
      "reason": "One sentence"
    }}
  ]
}}

Axes: accuracy(0.30), evidence(0.20), consistency(0.15), coverage(0.15),
usefulness(0.12), brevity(0.05), revision_quality(0.03)"""

    return f"""あなたは7軸でAIの回答を採点する客観的評価者です。

元の質問:
{question}

採点対象の全回答:
{responses_text}

上記に登場した全AIを全7軸（各0〜10）で採点してください。
自己採点も必須（システムが自動で0.5倍ペナルティを適用）。
エラーがあったAIは全軸0点。

有効なJSONのみを返してください（コードフェンス不可）:
{{
  "scores": [
    {{
      "target_ai": "Claude",
      "accuracy": 8.5,
      "evidence": 7.0,
      "consistency": 8.0,
      "coverage": 7.5,
      "usefulness": 8.0,
      "brevity": 6.5,
      "revision_quality": 7.0,
      "reason": "1文での説明"
    }}
  ]
}}

採点軸: accuracy(0.30), evidence(0.20), consistency(0.15), coverage(0.15),
usefulness(0.12), brevity(0.05), revision_quality(0.03)"""


# ─────────────────────────────────────────────
# シーン自動判定プロンプト
# ─────────────────────────────────────────────

def scene_detection_prompt(question: str) -> str:
    """Geminiによるシーン自動判定プロンプト"""
    return f"""Classify the following question into exactly ONE of 4 scenes. Return a single-line JSON only.

Scenes:
- "implementation": coding, step-by-step tasks, how-to, building, setup
- "decision": choosing options, pros/cons, should-I questions, strategy
- "logic_check": reviewing arguments/text for flaws, biases, logical errors
- "research": information gathering, investigation design, finding sources, competitive analysis, technology trend research. IMPORTANT: even if the question uses the verb "design" or "plan", classify as "research" if the subject is information gathering or investigation. Example: "design a method to investigate competitors' technology trends" → "research"

Question: {question}

Output EXACTLY this JSON on ONE LINE (no newlines, no code fences):
{{"scene":"implementation","confidence":0.90,"reason":"brief reason"}}"""

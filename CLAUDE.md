# AI Scene Router System — 実装指示書

`~/AI-Brain/projects/ai-debate-system` を読んで、以下の仕様で全ファイルを実装してください。
完了後に curl で動作確認し、git push してください。

---

## システム概要

4つのAI（Claude / ChatGPT / Gemini / Grok）がシーンに応じた役割分担で協調するシステム。
各AIの強みを活かし、Lead AIが主回答を担い、Support AIが補完・検証・実務化を行う。

```
Step 0（自動モード時）: Gemini-flash がシーン自動判定 → フロントに表示・変更可能
Step 1:                Lead AI が主回答を生成
Step 2..N:             Support AI がフロー定義に従い Sequential / Parallel で介入
[Optional]:            Scorer が全回答を7軸採点（シーン別デフォルト設定あり）
```

### MVP 実装シーン（4シーン）

| ID | シーン名 | Lead AI | Support AIs | フロー型 | Scorer デフォルト |
|---|---|---|---|---|---|
| `implementation` | 実装・タスク分解 | ChatGPT | Claude → Grok | Sequential | OFF |
| `decision` | 意思決定支援 | Claude | Gemini ‖ ChatGPT | Sequential→Parallel | ON |
| `logic_check` | 論理チェック | Claude | ChatGPT → Gemini | Sequential | ON |
| `research` | 情報収集・リサーチ設計 | Grok | Gemini ‖ Claude | Sequential→Parallel | OFF |

---

## ファイル構成

```
ai-debate-system/
├── CLAUDE.md
├── Makefile
├── docker-compose.yml
├── nginx.conf
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── models.py
│   ├── clients.py
│   ├── prompts.py
│   ├── scorer.py
│   ├── db.py
│   ├── scene_router.py
│   ├── scene_detector.py
│   ├── flow_executor.py
│   └── test_mock.py
└── frontend/
    └── index.html
```

---

## 要件

### backend/requirements.txt

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
anthropic>=0.42.0
openai>=1.59.0
google-genai>=1.0.0
python-dotenv==1.0.1
pydantic>=2.10.0
httpx>=0.28.0
asyncpg>=0.30.0
```

---

### backend/models.py

```python
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel

class AIName(str, Enum):
    CLAUDE   = "Claude"
    CHATGPT  = "ChatGPT"
    GEMINI   = "Gemini"
    GROK     = "Grok"

class SceneName(str, Enum):
    IMPLEMENTATION = "implementation"
    DECISION       = "decision"
    LOGIC_CHECK    = "logic_check"
    RESEARCH       = "research"

class StepRole(str, Enum):
    LEAD               = "lead"
    SUPPORT_CRITIC     = "support_critic"
    SUPPORT_ORGANIZER  = "support_organizer"
    SUPPORT_VALIDATOR  = "support_validator"
    SUPPORT_EXECUTOR   = "support_executor"
    SUPPORT_REWRITER   = "support_rewriter"
    SUPPORT_CONFIDENCE = "support_confidence"
    SUPPORT_UNCERTAINTY = "support_uncertainty"
    SUPPORT_HYPOTHESIS = "support_hypothesis"
    SCORER             = "scorer"

class FlowType(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL   = "parallel"

class FlowStep(BaseModel):
    step_index: int
    ai: AIName
    role: StepRole
    flow_type: FlowType          # このステップ群内での実行方式
    prompt_key: str
    depends_on: List[int] = []   # 入力として使う step_index リスト（空=全前ステップ）

class SceneConfig(BaseModel):
    scene: SceneName
    steps: List[FlowStep]
    scorer_available: bool
    scorer_default: bool

class FlowRequest(BaseModel):
    question: str
    scene: SceneName
    enable_scorer: bool
    openai_api_key: str
    gemini_api_key: str
    grok_api_key: str
    language: str = "ja"
    model_overrides: dict = {}   # {"Claude": "claude-haiku-4-5"} 等

class StepResponse(BaseModel):
    id: str
    step_index: int
    ai: AIName
    role: StepRole
    content: str
    error: Optional[str] = None
    timestamp: float

class ScoreDetail(BaseModel):
    scorer_ai: AIName
    target_ai: AIName
    is_self: bool
    accuracy: float
    evidence: float
    consistency: float
    coverage: float
    usefulness: float
    brevity: float
    revision_quality: float
    weighted_total: float
    reason: str

class DetectRequest(BaseModel):
    question: str
    gemini_api_key: str

class DetectResponse(BaseModel):
    scene: SceneName
    confidence: float
    reason: str
```

---

### backend/clients.py

- `call_claude / call_chatgpt / call_gemini / call_grok` の4関数
- 各関数の引数: `prompt: str, max_tokens: int, language: str, model: str = ""`
  - `model` 空文字のときデフォルトモデルを使用
- デフォルトモデル:
  - Claude: `claude-opus-4-5`
  - ChatGPT: `gpt-4o`
  - Gemini: `gemini-2.0-flash`
  - Grok: `grok-2-1212`
- Gemini は `google-genai` SDK（`genai.Client` + `aio.models.generate_content`）を使用
- Grok は OpenAI 互換クライアントで `base_url="https://api.x.ai/v1"`
- 全関数に指数バックオフのリトライ（最大2回）
- API キーは各関数の引数として受け取る（`api_key: str`）
  - Claude のみ環境変数 `ANTHROPIC_API_KEY` をフォールバックとして使用
  - それ以外は引数必須（空文字の場合は即座に ValueError を raise）

```python
async def call_claude(prompt: str, max_tokens: int, language: str, model: str = "", api_key: str = "") -> str: ...
async def call_chatgpt(prompt: str, max_tokens: int, language: str, model: str = "", api_key: str = "") -> str: ...
async def call_gemini(prompt: str, max_tokens: int, language: str, model: str = "", api_key: str = "") -> str: ...
async def call_grok(prompt: str, max_tokens: int, language: str, model: str = "", api_key: str = "") -> str: ...
```

---

### backend/prompts.py

以下のプロンプト生成関数を実装する。全関数は `language: str` を受け取り、"ja"/"en" で出力言語を切り替える。

#### Lead プロンプト

```python
def lead_implementation(question: str, language: str) -> str:
    """
    ChatGPT lead: 実装・タスク分解
    - ステップバイステップの完全な手順リストを生成
    - 各ステップにチェックボックス形式で出力
    - 前提条件・必要ツール・所要時間の目安も含める
    """

def lead_decision(question: str, language: str) -> str:
    """
    Claude lead: 意思決定支援
    - 論点の骨格を構築
    - スティールマン（最強の反論）を明示
    - 前提・リスク・代替案を列挙
    - Popper の反証可能性基準で論点を整理
    """

def lead_logic_check(text: str, language: str) -> str:
    """
    Claude lead: 論理チェック
    - 論理の穴・隠れた前提・反論されやすい箇所を指摘
    - バイアスの種類を分類して列挙
    - Toulmin モデルに基づき構造化して提示
    """

def lead_research(question: str, language: str) -> str:
    """
    Grok lead: 情報収集・リサーチ設計
    - 調査計画を立案
    - Evidence Table（情報源種別・信頼度・優先度付き）を生成
    - タイムボックスごとの調査ステップを設計
    """
```

#### Support プロンプト

```python
def support_critic(question: str, lead_output: str, language: str) -> str:
    """
    Claude support: 抜け漏れ・前提の見落とし・反証を指摘
    lead_output を受け取り、具体的な欠陥箇所を列挙
    """

def support_organizer(question: str, lead_output: str, critic_output: str, language: str) -> str:
    """
    Grok support: 記録体系化
    lead + critic の出力を受け取り、Evidence Table・タイムボックス形式に整理
    """

def support_validator(question: str, lead_output: str, language: str) -> str:
    """
    Gemini support: 確信度数値化
    lead_output の各主張に対しベイズ的確信度（0〜1）を付与して評価
    """

def support_executor(question: str, lead_output: str, language: str) -> str:
    """
    ChatGPT support: 実務アクションプラン化
    lead_output を受け取り、明日から実行できる具体的なアクションに変換
    """

def support_rewriter(original_text: str, critic_output: str, language: str) -> str:
    """
    ChatGPT support: 論理チェック後の言い直し
    元テキストと指摘を受け取り、修正案を提示
    """

def support_confidence(original_text: str, critic_output: str, rewritten_output: str, language: str) -> str:
    """
    Gemini support: 修正後の論理強度スコアリング
    修正前後の論理強度を確信度スコアで比較評価
    """

def support_uncertainty(research_plan: str, language: str) -> str:
    """
    Gemini support: 調査計画の不確実性マーキング
    調査計画内のリスク・見落とし箇所に確信度を付与
    """

def support_hypothesis(research_plan: str, language: str) -> str:
    """
    Claude support: 調査仮説の論理的妥当性検証
    調査計画の仮説が論理的に成立するかを検証
    """
```

#### Scorer プロンプト

```python
def scoring_prompt(question: str, step_responses: list[dict], language: str) -> str:
    """
    全ステップの回答を全文含める（要約しない）
    7軸スコアの JSON 形式での出力を厳命（コードフェンスなし）
    自己採点も必須（システム側で 0.5 倍ペナルティ適用）
    """
```

#### シーン自動判定プロンプト

```python
def scene_detection_prompt(question: str) -> str:
    """
    以下4シーンのいずれかに分類し、JSON のみを返すよう指示。
    コードフェンス不可。
    {
      "scene": "implementation" | "decision" | "logic_check" | "research",
      "confidence": 0.0〜1.0,
      "reason": "判定理由（1〜2文）"
    }
    シーン定義をプロンプト内に明示すること。
    """
```

---

### backend/scorer.py

旧システムから流用。以下の関数を維持する。

- `WEIGHTS` 定数（合計 1.0）
  - accuracy:0.30 / evidence:0.20 / consistency:0.15 / coverage:0.15 / usefulness:0.12 / brevity:0.05 / revision_quality:0.03
- `parse_score_response(content: str) -> dict | None`
  - コードフェンス除去 → JSON パース、失敗時 None
- `calculate_weighted_total(raw: dict, is_self: bool) -> float`
  - 各軸 × 重み × 10 で 0〜100 換算
  - `is_self=True` のとき 0.5 倍
- `aggregate_final_scores(score_details: list[ScoreDetail]) -> dict`
  - AI 別 `weighted_total` の平均 + ランク付け
- `build_ranking(aggregated: dict) -> list[str]`

---

### backend/scene_router.py

シーンごとの `SceneConfig`（`FlowStep` のリスト）を定義・返す。

```python
from models import *

def get_scene_config(scene: SceneName) -> SceneConfig:
    """
    4シーンの SceneConfig を返す。
    FlowStep.depends_on は入力として使う step_index リストで指定。
    例:
      step_index=0: Lead（depends_on=[]）
      step_index=1: Support（depends_on=[0]）
      step_index=2: Support（depends_on=[0]）  ← 0と並列
      step_index=3: Support（depends_on=[1,2]）← 1,2両方を入力に使う
    """
```

#### 各シーンの FlowStep 定義

**implementation**
```
step 0: ChatGPT / LEAD            / SEQUENTIAL / lead_implementation
step 1: Claude  / SUPPORT_CRITIC  / SEQUENTIAL / support_critic         / depends_on=[0]
step 2: Grok    / SUPPORT_ORGANIZER / SEQUENTIAL / support_organizer    / depends_on=[0,1]
```

**decision**
```
step 0: Claude  / LEAD              / SEQUENTIAL / lead_decision
step 1: Gemini  / SUPPORT_VALIDATOR / PARALLEL   / support_validator    / depends_on=[0]
step 2: ChatGPT / SUPPORT_EXECUTOR  / PARALLEL   / support_executor     / depends_on=[0]
```

**logic_check**
```
step 0: Claude  / LEAD               / SEQUENTIAL / lead_logic_check
step 1: ChatGPT / SUPPORT_REWRITER   / SEQUENTIAL / support_rewriter    / depends_on=[0]
step 2: Gemini  / SUPPORT_CONFIDENCE / SEQUENTIAL / support_confidence  / depends_on=[0,1]
```

**research**
```
step 0: Grok   / LEAD                  / SEQUENTIAL / lead_research
step 1: Gemini / SUPPORT_UNCERTAINTY   / PARALLEL   / support_uncertainty / depends_on=[0]
step 2: Claude / SUPPORT_HYPOTHESIS    / PARALLEL   / support_hypothesis  / depends_on=[0]
```

---

### backend/scene_detector.py

```python
async def detect_scene(question: str, gemini_api_key: str) -> DetectResponse:
    """
    - gemini-2.0-flash を使用（固定）
    - scene_detection_prompt を呼び出し
    - JSON パース失敗時は SceneName.DECISION をデフォルトとして返す
    - confidence が 0.5 未満の場合は reason に「自動判定の信頼度が低いため確認推奨」を付記
    """
```

---

### backend/flow_executor.py

```python
async def execute_flow(
    request: FlowRequest,
    scene_config: SceneConfig,
    on_step: Callable[[StepResponse], Awaitable[None]],
    pool,
    job_id: str,
) -> list[StepResponse]:
    """
    scene_config.steps の FlowStep リストを実行する。

    実行アルゴリズム:
    1. steps を step_index 順にソート
    2. depends_on が同一の steps 群は asyncio.gather で並列実行
       depends_on が前ステップを参照する steps は順次実行
    3. 各 step 完了後に on_step コールバックを呼ぶ（SSE 送信に使用）
    4. プロンプト構築:
       - step の prompt_key に対応する prompts.py の関数を呼び出す
       - depends_on の step_index に対応する StepResponse.content を入力として渡す
    5. API 呼び出しは clients.py の call_* 関数を使用
       - model は request.model_overrides から取得、なければ空文字（デフォルト）
       - api_key は request から取得
    6. エラー時は StepResponse.error にメッセージを格納し、後続ステップは
       error content を "（前ステップでエラーが発生しました）" として続行
    7. 各 StepResponse 完了後に db.save_response を呼ぶ
    """

async def execute_scorer(
    request: FlowRequest,
    step_responses: list[StepResponse],
    on_score: Callable[[ScoreDetail], Awaitable[None]],
    pool,
    job_id: str,
) -> list[ScoreDetail]:
    """
    全 StepResponse を対象に全 Lead/Support AI が採点。
    採点対象は Lead AI と全 Support AI の回答（SCORER ロール自身は除く）。
    採点は全 AI 並列で実行（asyncio.gather）。
    """
```

---

### backend/db.py

旧システムから流用・拡張。

- `asyncpg` で非同期 PostgreSQL 接続（環境変数 `DATABASE_URL`）
- DB 未接続時は全関数が警告ログのみで None / [] を返す
- `create_pool()` — 接続プール作成、失敗時 None
- `init_db(pool)` — 以下テーブルを `CREATE TABLE IF NOT EXISTS` で作成

```sql
CREATE TABLE IF NOT EXISTS scene_jobs (
    id TEXT PRIMARY KEY,
    question TEXT,
    scene TEXT,
    status TEXT,
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS step_responses (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    step_index INT,
    ai TEXT,
    role TEXT,
    content TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS step_scores (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    scorer_ai TEXT,
    target_ai TEXT,
    is_self BOOLEAN,
    accuracy FLOAT, evidence FLOAT, consistency FLOAT,
    coverage FLOAT, usefulness FLOAT, brevity FLOAT, revision_quality FLOAT,
    weighted_total FLOAT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

- `save_job(pool, job_id, question, scene)`
- `finish_job(pool, job_id)`
- `save_response(pool, job_id, resp: StepResponse)`
- `save_score(pool, job_id, score: ScoreDetail)`
- `get_recent_jobs(pool, limit=20) -> list[dict]`
- `get_job_detail(pool, job_id) -> dict`（step_responses + step_scores を返す）

---

### backend/main.py

- FastAPI アプリ、バージョン `3.0.0`
- `lifespan` context manager
  - 起動時に `create_pool()` + `init_db()` を実行、プールを `app.state.pool` に格納
  - DB 未接続でもアプリは起動継続

#### エンドポイント

**`GET /health`**
```json
{"status": "ok", "version": "3.0.0", "db": true}
```

**`POST /api/scene/detect`**
- リクエスト: `DetectRequest`
- レスポンス: `DetectResponse`
- Gemini-flash でシーン判定して返す

**`GET /api/scenes`**
- 全シーン定義の一覧を返す（フロントのシーン選択UIで使用）
```json
[
  {
    "id": "implementation",
    "name": "実装・タスク分解",
    "lead_ai": "ChatGPT",
    "support_ais": ["Claude", "Grok"],
    "scorer_default": false
  },
  ...
]
```

**`POST /api/flow/stream`** — SSE エンドポイント
- リクエスト: `FlowRequest`（JSON body）
- `asyncio.Queue` で producer / consumer を分離
- SSE イベント形式:
```
data: {"type": "step_start",    "step_index": 0, "ai": "ChatGPT", "role": "lead"}
data: {"type": "step_complete", "step_index": 0, "ai": "ChatGPT", "role": "lead", "data": StepResponse}
data: {"type": "score_complete","data": ScoreDetail}
data: {"type": "complete",      "total_steps": N, "job_id": "..."}
```
- 1秒タイムアウトで `: keepalive` を送信
- job_id は `uuid4` で生成し、`db.save_job` で保存

**`GET /api/history`**
- 最近 20 件のジョブ一覧（DB 未接続時は空リスト）

**`GET /api/history/{job_id}`**
- 指定ジョブの全ステップ回答・スコア

---

### backend/test_mock.py

- `clients.py` の `call_*` 関数をモックに差し替えて全フローを検証
- 4シーン全てをテスト

```python
# モックレスポンス判定ロジック
def mock_response(prompt: str) -> str:
    if "accuracy" in prompt:
        return MOCK_SCORE_JSON      # 採点JSON
    elif "実装" in prompt or "手順" in prompt:
        return MOCK_IMPLEMENTATION  # 実装回答スタブ
    elif "意思決定" in prompt or "反証" in prompt:
        return MOCK_DECISION        # 意思決定スタブ
    elif "論理" in prompt or "バイアス" in prompt:
        return MOCK_LOGIC           # 論理チェックスタブ
    elif "調査" in prompt or "Evidence" in prompt:
        return MOCK_RESEARCH        # リサーチスタブ
    else:
        return MOCK_DEFAULT
```

#### アサート内容（シーンごと）

| シーン | 期待ステップ数 | Scorer ON | 期待スコア件数 |
|---|---|---|---|
| implementation | 3 | OFF | 0 |
| decision | 3（1 + 2並列） | ON | 3（lead+2support） |
| logic_check | 3 | ON | 3 |
| research | 3（1 + 2並列） | OFF | 0 |

全シーンで:
- エラー 0 件
- 全 StepResponse に `content` が存在すること

---

### docker-compose.yml

旧システムから変更なし。

- `postgres:16-alpine` サービス
  - `POSTGRES_DB=debate`, `POSTGRES_USER=debate`, `POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-debate}`
  - healthcheck: `pg_isready -U debate -d debate`
  - volume: `postgres_data`
- `backend` サービス
  - `depends_on: postgres（condition: service_healthy）`
  - 環境変数: `ANTHROPIC_API_KEY`, `DATABASE_URL=postgresql://debate:debate@postgres:5432/debate`
- `frontend` サービス: nginx:alpine、ポート 3000
- `volumes: postgres_data:` をトップレベルに定義

---

### frontend/index.html

React 18 / ReactDOM / Babel / marked.js を CDN から読み込む。ビルドステップなし。

#### 定数

```javascript
const API_BASE = "http://localhost:8000"

const AI_COLORS = {
  Claude:  "#c084fc",
  ChatGPT: "#22d3a0",
  Gemini:  "#60a5fa",
  Grok:    "#fb923c",
}
const AI_BG = {
  Claude:  "#1e1030",
  ChatGPT: "#0d2720",
  Gemini:  "#0d1e30",
  Grok:    "#2a1508",
}
const ROLE_LABELS = {
  lead:               "🎯 Lead",
  support_critic:     "🔍 批評",
  support_organizer:  "📋 整理",
  support_validator:  "📊 検証",
  support_executor:   "⚡ 実行",
  support_rewriter:   "✏️ 言い直し",
  support_confidence: "📈 信頼度",
  support_uncertainty:"⚠️ 不確実性",
  support_hypothesis: "🧪 仮説検証",
  scorer:             "🏆 採点",
}
const WEIGHTS = {
  accuracy: 0.30, evidence: 0.20, consistency: 0.15,
  coverage: 0.15, usefulness: 0.12, brevity: 0.05, revision_quality: 0.03,
}
const SCENE_LABELS = {
  implementation: "実装・タスク分解",
  decision:       "意思決定支援",
  logic_check:    "論理チェック",
  research:       "情報収集・リサーチ設計",
}
```

#### CSS 変数（`:root`）

```css
--bg:#0f1117; --bg2:#1a1d27; --bg3:#232638;
--border:#2e3250; --text:#e2e4ef; --text2:#8b90ad; --text3:#5a6080;
--accent:#6366f1; --success:#22c55e; --error:#ef4444; --warning:#f59e0b;
```

#### 設定の保存

config（APIキー・言語・シーン等）を localStorage に保存・復元する。

---

#### SceneSelector コンポーネント

モード切替ボタン（手動 / 自動）付きのシーン選択UI。

**手動モード**
- `GET /api/scenes` で取得したシーン一覧を選択肢として表示
- 各シーンカードに Lead AI・Support AI のバッジを表示
- 選択中シーンをハイライト

**自動モード**
- 質問入力後に「シーンを自動判定」ボタンを表示
- ボタン押下で `POST /api/scene/detect` を呼び出し
- 判定結果を以下の形式でカード表示:
  ```
  ┌──────────────────────────────────┐
  │  🤖 自動判定結果                 │
  │  シーン: 意思決定支援            │
  │  確信度: 87%                     │
  │  理由: ~~~                       │
  │  [このシーンで実行] [変更する]   │
  └──────────────────────────────────┘
  ```
- 「変更する」を押すと手動モードに切り替え
- `confidence < 0.5` の場合は警告スタイルで表示

---

#### ConfigPanel コンポーネント

- OpenAI / Gemini / Grok の API キー入力（type="password"）
- 言語切替（日本語 / English）
- Scorer ON/OFF トグル（シーンのデフォルト値を初期値として使用）
- 各AIのモデルオーバーライド入力（空欄=デフォルトモデル）
  - 例: Claude に `claude-haiku-4-5` を指定してコスト削減
- 折りたたみ / 展開トグル

---

#### FlowTimeline コンポーネント

実行中・完了済みのフローを縦のタイムライン形式で表示。

- 各ステップを StepCard として表示
- 並列実行されるステップは横並びで表示
- 実行前: グレーアウト
- 実行中: スピナー + AI カラーのボーダーアニメーション
- 完了: AI カラーのボーダー + 展開/折りたたみ可能

---

#### StepCard コンポーネント

- ヘッダー: `[AI名バッジ] [ROLEラベル] [Step N]`
- コンテンツ: marked.js で Markdown レンダリング
- クリックで展開 / 折りたたみ
- ロール別の左ボーダーカラー:
  - `lead`: AI_COLORS[ai]
  - `support_*`: AI_COLORS[ai]（薄め、opacity 0.7）
  - `scorer`: #22c55e（緑）
- エラー時は赤テキスト

---

#### ScoreBoard コンポーネント

旧システムの実装を流用。

- RadarChart（SVG 320×320、7軸、ライブラリ不使用）
- AI別 weighted_total の平均バーグラフ
- 🥇🥈🥉 メダル付きランキング
- 採点者別ボタンで 7軸スコア詳細を切り替え

---

#### ProgressBar コンポーネント

- 現在ステップ名を表示（`${ROLE_LABELS[role]} — ${ai}`）
- 完了ステップ数 / 全ステップ数とパーセンテージ
- アニメーションするプログレスバー

---

#### HistoryModal コンポーネント

- ヘッダー右上に「📂 履歴」ボタン
- `GET /api/history` で直近 20 件を一覧表示
  - 表示項目: 日時・シーン名・質問（先頭 50 文字）・ステータス
- 行クリックで `GET /api/history/{job_id}` を fetch し結果を再描画

---

#### App（メインコンポーネント）

- SSE で `POST /api/flow/stream` に接続
- `step_complete` イベントで `stepResponses` state に追記
- `score_complete` イベントで `scoreDetails` state に追記
- 新着ステップは 3 秒間 fade-in アニメーション
- 停止ボタン: AbortController で SSE を切断
- JSON 書き出しボタン: `{config, scene, stepResponses, scoreDetails}` を Blob → a タグでダウンロード
- 完了後: job_id と合計ステップ数を表示

---

## 完了後の確認手順

```bash
# モックテスト（APIキー・DB 不要）
cd backend && python test_mock.py
# 期待: 4シーン全て通過、エラー 0 件

# サーバー起動確認
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/scenes
curl -s http://localhost:8000/api/history

# シーン自動判定の確認（Gemini API キーが必要）
curl -s -X POST http://localhost:8000/api/scene/detect \
  -H "Content-Type: application/json" \
  -d '{"question":"このビジネス戦略の論理的な穴を見つけてください","gemini_api_key":"YOUR_KEY"}'
# 期待: {"scene":"logic_check", "confidence":0.8以上, "reason":"..."}

# フロントエンド確認
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/
```

完了後、git push してください。

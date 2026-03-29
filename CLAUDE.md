# AI Debate System — 実装指示書

`~/AI-Brain/projects/ai-debate-system` を読んで、以下の仕様で全ファイルを実装してください。
完了後に curl で動作確認し、git push してください。

---

## システム概要

4つのAI（Claude / ChatGPT / Gemini / Grok）が同一の質問に対して討論するシステム。

```
Phase 0:        初回回答  — 4AI 並列
Phase 1..N:     相互評価  — 各AIが他3AIを評価（12件 × N ラウンド）
Phase revision: 自己改訂  — 各AIが受けた批評を踏まえて改訂版を生成
Phase scoring:  採点      — 各AIが全回答を7軸 JSON で採点
```

2ラウンド・4AI の場合: 4 + 24 + 4 + 4 = **36件**のレスポンス

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
│   ├── debate.py
│   ├── clients.py
│   ├── models.py
│   ├── prompts.py
│   ├── scorer.py
│   ├── db.py
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

- `AIName` enum: CLAUDE / CHATGPT / GEMINI / GROK
- `ResponseType` enum: INITIAL / EVALUATION / REVISION / SCORING
- `DebateResponse` モデル
  - `id: str`
  - `ai: AIName`
  - `round: int`
  - `response_type: ResponseType`
  - `phase: str`（"initial" / "evaluation" / "revision" / "scoring"）
  - `target_ai: Optional[AIName]`
  - `revision_of: Optional[str]`（改訂元レスポンスの id）
  - `content: str`
  - `error: Optional[str]`
  - `timestamp: float`
- `ScoreDetail` モデル
  - `scorer_ai: AIName`
  - `target_ai: AIName`
  - `is_self: bool`
  - 7軸スコア: `accuracy / evidence / consistency / coverage / usefulness / brevity / revision_quality`（各 float 0〜10）
  - `weighted_total: float`（0〜100）
  - `reason: str`
- `DebateConfig` モデル
  - `question: str`
  - `rounds: int`（デフォルト 2、1〜5）
  - `openai_api_key / gemini_api_key / grok_api_key: str`
  - `enabled_ais: List[AIName]`（デフォルト全4AI）
  - `language: Literal["ja", "en"]`（デフォルト "ja"）
  - `enable_revision: bool`（デフォルト True）
  - `max_tokens_initial / max_tokens_eval / max_tokens_revision / max_tokens_score: int`
  - `model_eval / model_revision / model_scoring: str`（空文字 = デフォルトモデル）

---

### backend/clients.py

- `call_claude / call_chatgpt / call_gemini / call_grok` の4関数
- 各関数の引数: `prompt, max_tokens, language, model`（model 空文字のときデフォルトモデルを使用）
- デフォルトモデル: claude-opus-4-5 / gpt-4o / gemini-2.0-flash / grok-2-1212
- Gemini は `google-genai` SDK（`genai.Client` + `aio.models.generate_content`）を使用
- Grok は OpenAI 互換クライアントで `base_url="https://api.x.ai/v1"`
- 全関数に指数バックオフのリトライ（2回）

---

### backend/scorer.py

- `WEIGHTS` 定数（合計 1.0）
  - accuracy:0.30 / evidence:0.20 / consistency:0.15 / coverage:0.15 / usefulness:0.12 / brevity:0.05 / revision_quality:0.03
- `parse_score_response(content) -> dict | None`
  - コードフェンスを除去して JSON パース、失敗時 None
- `calculate_weighted_total(raw, is_self) -> float`
  - 各軸スコア × 重み × 10 で 0〜100 換算
  - `is_self=True` のとき 0.5 倍
- `aggregate_final_scores(score_details) -> dict`
  - AI 別に `weighted_total` の平均を計算しランク付け
- `build_ranking(aggregated) -> list[str]`
  - スコア降順の AI 名リスト

---

### backend/db.py

- `asyncpg` で非同期 PostgreSQL 接続（環境変数 `DATABASE_URL` から取得）
- DB 未接続時は全関数が警告ログのみ出して None / [] を返す（例外を上位に伝播させない）
- `create_pool()` — 接続プール作成、失敗時 None
- `init_db(pool)` — 以下3テーブルを `CREATE TABLE IF NOT EXISTS` で作成
  - `debate_jobs`（id, question, status, max_rounds, started_at, finished_at）
  - `ai_responses`（id, job_id, ai, round, phase, response_type, target_ai, revision_of, content, error, created_at）
  - `ai_scores`（id, job_id, scorer_ai, target_ai, is_self, 7軸 float, weighted_total, reason, created_at）
- `save_job(pool, job_id, question, max_rounds)`
- `finish_job(pool, job_id)`
- `save_response(pool, job_id, resp: DebateResponse)`
- `save_score(pool, job_id, score: ScoreDetail)`
- `get_recent_jobs(pool, limit=20) -> list[dict]`
- `get_job_responses(pool, job_id) -> dict`

---

### backend/prompts.py

- `initial_prompt(question, language)` — 包括的な初回回答を求めるプロンプト
- `evaluation_prompt(question, target_ai, prev_responses, round_num, language)` — 正確性・完全性・論理性・洞察力・改善提案の6観点で評価を求めるプロンプト
- `revision_prompt(question, my_ai, my_initial_content, critiques, language)`
  - 他 AI からの批評リストを受け取り改訂版を生成するプロンプト
  - 冒頭に【改訂点】セクションで変更箇所と理由を明示するよう指示
  - 改訂不要な場合は「【改訂不要】理由: ...」と返すよう指示
- `scoring_prompt_v2(question, all_responses, ai_names, language)`
  - 全回答を全文そのままプロンプトに含める（要約しない）
  - 7軸スコアの JSON 形式での出力を厳命する（コードフェンスなし）
  - 自分自身へのスコアも必須（システム側で 0.5 倍ペナルティを適用する旨を添える）
  - エラーの AI は全軸 0 点とするよう指示

---

### backend/debate.py

- `_call_ai(ai, prompt, config, max_tokens, semaphore, model_override)` — 各 AI クライアントへのディスパッチ
- `run_debate(config, on_response, pool, job_id)` — 4フェーズのオーケストレーション
  - `asyncio.Semaphore(4)` で同時実行数を制限
  - 各フェーズで `asyncio.as_completed` を使用し完了順に即座に `on_response` を呼ぶ
  - ループ内タスク生成前に必ず `snapshot = list(all_responses)` でスナップショットを取る
  - **Phase 0**: 初回回答（並列）
  - **Phase 1..N**: 相互評価（各 AI が他 AI の前ラウンド回答を評価、並列）
  - **Phase revision**（`enable_revision=True` のとき）
    - 各 AI が `target_ai == 自分` の evaluation を収集して改訂版を生成
    - `response_type=REVISION`、`revision_of=初回回答の id` をセット
  - **Phase scoring**
    - `scoring_prompt_v2` を使用（全文渡し）
    - 採点 JSON パース後に `ScoreDetail` を生成して `db.save_score` で保存
  - 各レスポンス完了後に `db.save_response` を呼ぶ

---

### backend/main.py

- FastAPI アプリ、バージョン `2.0.0`
- `lifespan` context manager
  - 起動時に `create_pool()` + `init_db()` を実行、プールを `app.state.pool` に格納
  - DB 未接続でもアプリは起動継続
  - シャットダウン時にプールをクローズ
- `GET /health` — ステータスと DB 接続状態を返す
- `POST /api/debate/stream` — SSE エンドポイント
  - `asyncio.Queue` で producer / consumer を分離
  - 回答完了ごとに `data: {"type": "response", "data": ...}` を送信
  - 全完了時に `data: {"type": "complete", "total": N, "job_id": "..."}` を送信
  - 1秒タイムアウトで `: keepalive` を送信
- `GET /api/debate/history` — 最近 20 件のジョブ一覧（DB 未接続時は空リスト）
- `GET /api/debate/history/{job_id}` — 指定ジョブの全レスポンス・スコア

---

### backend/test_mock.py

- `_call_ai` をモックに差し替えて全フロー（4AI・2ラウンド・改訂あり）を検証
- 期待レスポンス数: **36件**（4 + 24 + 4 + 4）
- スタブ判定: `"accuracy"` が含まれるプロンプト → スコア JSON を返す / `"改訂"` が含まれる → 改訂スタブを返す / それ以外 → 初回回答スタブ
- アサート内容
  - レスポンス数が 36 件
  - エラー 0 件
  - revision レスポンスが 4 件、かつ全て `revision_of` が設定されている
  - scoring レスポンスが 4 件

---

### docker-compose.yml

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

```
API_BASE = "http://localhost:8000"
AI_COLORS = { Claude:"#c084fc", ChatGPT:"#22d3a0", Gemini:"#60a5fa", Grok:"#fb923c" }
AI_BG     = { Claude:"#1e1030", ChatGPT:"#0d2720", Gemini:"#0d1e30", Grok:"#2a1508" }
WEIGHTS   = { accuracy:0.30, evidence:0.20, consistency:0.15, coverage:0.15,
              usefulness:0.12, brevity:0.05, revision_quality:0.03 }
```

#### CSS 変数（`:root`）

```
--bg:#0f1117; --bg2:#1a1d27; --bg3:#232638;
--border:#2e3250; --text:#e2e4ef; --text2:#8b90ad; --text3:#5a6080;
--accent:#6366f1; --success:#22c55e; --error:#ef4444;
```

#### 設定の保存

config（APIキー含む）を localStorage に保存・復元する。

#### ConfigPanel

- 参加 AI 選択（最低 2 つ必須）
- 評価ラウンド数: 1〜5 のボタン選択（`config.rounds` に対応、選択中をハイライト）
- 自己改訂フェーズ ON/OFF トグル（`config.enable_revision` に対応）
- OpenAI / Gemini / Grok の API キー入力（type="password"）
- 言語切替（日本語 / English）
- API 呼び出し合計回数をリアルタイム表示
  - `n + n*(n-1)*r + (enable_revision ? n : 0) + n`（n=参加AI数、r=ラウンド数）
- 折りたたみ / 展開トグル

#### タブ UI

メイン表示エリアに以下のタブを設置する。

| タブ | 表示内容 |
|---|---|
| 全体 | 全レスポンスをフェーズ順に表示（RoundSection を使用） |
| Claude / ChatGPT / Gemini / Grok | そのAIに関するレスポンスのみ（下記参照） |
| スコア | ScoreBoard（レーダーチャート含む）と RevisionLog |

AI 個別タブの表示区分:
- **自分の回答**: `ai === タブ名` の initial / revision / scoring
- **自分が行った評価**: `ai === タブ名` の evaluation（評価対象 AI を明示）
- **自分が受けた評価**: `target_ai === タブ名` の evaluation（評価者 AI を明示）

各タブの右に未読バッジ（新着レスポンス数）を表示し、タブを開いたらクリアする。

#### ResponseCard

- クリックで展開 / 折りたたみ
- フェーズ別の左ボーダーカラー
  - initial / evaluation: AI_COLORS[ai]
  - revision: #a855f7（紫）、ヘッダーに ✏ マーク
  - scoring: #22c55e（緑）
- コンテンツは marked.js で Markdown レンダリング
- エラー時は赤テキスト

#### ProgressBar

- 現在フェーズ名を表示（初回回答中 / 相互評価中 Round N / 自己改訂中 / 採点中）
- 完了数 / 合計数とパーセンテージ
- アニメーションするプログレスバー

#### RadarChart（SVG のみ、ライブラリ不使用）

- SVG 320×320、7軸のレーダーを正多角形で描画
- 各 AI のスコアを AI_COLORS で色分けした polygon で重ね表示（fill-opacity:0.2、stroke-width:2）
- 外周に軸ラベル（正確性 / 根拠 / 一貫性 / 網羅性 / 実用性 / 簡潔さ / 改訂品質）
- チャート下に凡例

#### ScoreBoard

- RadarChart を上部に配置
- 採点レスポンスの JSON をパースして AI 別平均 weighted_total を計算
  - 自己採点は 0.5 倍（`scorer_ai === target_ai` のとき）
- 平均スコアのバーグラフ（AI 別、AI_COLORS で色付け）
- 🥇🥈🥉 メダル付きランキング
- 採点者別ボタンで 7軸スコア詳細 / reason / overall_analysis を切り替え表示

#### RevisionLog

- revision レスポンスがある場合のみ表示
- 各 AI について初回回答（`revision_of` で紐付け）と改訂版を左右に並べて表示
- 「改訂不要」を含む場合はグレーアウト

#### 履歴モーダル

- ヘッダー右上に「📂 履歴」ボタン
- `/api/debate/history` を fetch して直近 20 件を一覧表示
- 行クリックで `/api/debate/history/{job_id}` を fetch し結果を再描画

#### App（メインコンポーネント）

- SSE で `POST /api/debate/stream` に接続し、response イベントを受信するたびに responses state に追記
- 新着レスポンスは 3 秒間 fade-in アニメーション付与
- 停止ボタン: AbortController で SSE を切断
- JSON 書き出しボタン: `{config, responses}` を Blob → a タグでダウンロード
- 完了後: job_id と合計件数を表示

---

## 完了後の確認手順

```bash
# モックテスト（APIキー・DB 不要）
cd backend && python test_mock.py
# 期待: 実際レスポンス数: 36、✅ 全テスト通過

# サーバー起動確認
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/debate/history

# フロントエンド確認
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/
```

完了後、git push してください。

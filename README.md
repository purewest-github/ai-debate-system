# AI Debate System

4つのAI（Claude / ChatGPT / Gemini / Grok）が同一の質問に対して討論するシステムです。

## 概要

```
Phase 0:        初回回答  — 4AI 並列
Phase 1..N:     相互評価  — 各AIが他3AIを評価（12件 × N ラウンド）
Phase revision: 自己改訂  — 各AIが受けた批評を踏まえて改訂版を生成
Phase scoring:  採点      — 各AIが全回答を7軸 JSON で採点
```

2ラウンド・4AI の場合: 4 + 24 + 4 + 4 = **36件** のレスポンス

## スクリーンショット

| 討論画面 | スコアボード |
|---|---|
| タブUI・各AIの回答をリアルタイム表示 | RadarChart + ランキング + 詳細スコア |

## 技術スタック

| 領域 | 技術 |
|---|---|
| バックエンド | FastAPI 0.115, Python 3.12 |
| AI SDK | Anthropic / OpenAI / Google GenAI |
| データベース | PostgreSQL 16 (asyncpg) |
| フロントエンド | React 18 + Babel + marked.js (CDN) |
| インフラ | Docker Compose, Nginx |

## セットアップ

### 前提条件

- Docker / Docker Compose
- 各AIのAPIキー（Anthropic は環境変数、その他はUI上で入力可）

### 1. 環境変数を設定

```bash
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY を設定
```

### 2. Docker で起動

```bash
make up
# または
docker-compose up -d
```

| サービス | URL |
|---|---|
| フロントエンド | http://localhost:3000 |
| バックエンド API | http://localhost:8000 |
| API ドキュメント | http://localhost:8000/docs |

### 3. ローカル開発（Docker なし）

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

フロントエンドは `frontend/index.html` を直接ブラウザで開くか、任意の HTTP サーバーで配信してください。

## 使い方

1. ブラウザで http://localhost:3000 を開く
2. **設定パネル**でAPIキー・参加AI・ラウンド数などを設定
3. 質問を入力して「討論開始」をクリック
4. 回答がリアルタイムにストリーミング表示される
5. **スコアタブ**でRadarChart・ランキング・改訂ログを確認

## 設定項目

| 項目 | デフォルト | 説明 |
|---|---|---|
| 参加AI | 全4AI | Claude / ChatGPT / Gemini / Grok（最低2つ） |
| 評価ラウンド数 | 2 | 1〜5 |
| 自己改訂 | ON | 批評を受けて回答を改訂するか |
| 言語 | 日本語 | ja / en |

## 採点軸（7軸）

| 軸 | 重み | 説明 |
|---|---|---|
| accuracy（正確性） | 30% | 情報の正確さと信頼性 |
| evidence（根拠） | 20% | 主張を支える証拠の質と量 |
| consistency（一貫性） | 15% | 論理の一貫性と矛盾のなさ |
| coverage（網羅性） | 15% | 質問に対する回答の網羅度 |
| usefulness（実用性） | 12% | 実際の役立ちやすさ |
| brevity（簡潔さ） | 5% | 冗長さを避けた簡潔な表現 |
| revision_quality（改訂品質） | 3% | 批評を受けた改善の質 |

自己採点には **0.5倍ペナルティ**が適用されます。

## API エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/health` | ヘルスチェック |
| POST | `/api/debate/stream` | 討論開始（SSE） |
| GET | `/api/debate/history` | 直近20件の履歴 |
| GET | `/api/debate/history/{job_id}` | 指定ジョブの詳細 |

## ファイル構成

```
ai-debate-system/
├── backend/
│   ├── main.py        # FastAPI アプリ・SSE エンドポイント
│   ├── debate.py      # 4フェーズオーケストレーション
│   ├── clients.py     # 各AI APIクライアント
│   ├── models.py      # Pydantic モデル
│   ├── prompts.py     # プロンプトテンプレート
│   ├── scorer.py      # 採点ロジック
│   ├── db.py          # PostgreSQL (asyncpg)
│   └── test_mock.py   # モックテスト
├── frontend/
│   └── index.html     # React アプリ（CDN、ビルドなし）
├── docker-compose.yml
├── nginx.conf
└── Makefile
```

## テスト

```bash
# モックテスト（APIキー・DB 不要）
make test
# 期待: 実際レスポンス数: 36、✅ 全テスト通過
```

## Makefile コマンド

```bash
make up       # Docker Compose で起動
make down     # 停止
make test     # モックテスト実行
make logs     # 全サービスのログ
make logs-backend  # バックエンドのみ
```

## ライセンス

MIT

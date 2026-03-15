# NextQuant — AI-Powered Algorithmic Trading Platform

> An end-to-end autonomous trading system combining real-time market data ingestion, ML ensemble predictions, causal analysis, and Claude AI decision-making — deployed as a multi-tenant SaaS.

---

## What is NextQuant?

NextQuant is a full-stack algorithmic trading platform that autonomously analyzes markets, generates predictions, and executes trades. It combines:

- **Real-time data ingestion** via WebSocket (Alpaca, Finnhub, Bitget, Mock fallback)
- **84-feature ML ensemble** (LGBM + LSTM + GARCH + 5-state HMM regime detection)
- **Causal analysis** (Granger causality + Transfer Entropy)
- **Claude AI decision layer** — LLM validates every trade before execution
- **Kelly Criterion sizing** — risk-adjusted position sizing per signal
- **Risk Guardian veto layer** — hard stops before any order is placed
- **SaaS multi-tenant** — per-user broker connections, risk profiles, and billing (Stripe)

---

## Architecture

```
Market Sources (Alpaca / Finnhub / Bitget / Mock)
  │
  ▼
Rust Engine  ──►  NATS  ──►  Python ML  ──►  NATS  ──►  Trading Agent  ──►  Broker APIs
  │                            │                              │
  ▼                            ▼                              ▼
QuestDB                   QuestDB                       PostgreSQL
(market_data)          (ml_signals,                   (orders, audit,
                        feature_store)                  claude_decisions)
                                                             │
                                                             ▼
                                                       Next.js Frontend
                                                    (SSE streams → Browser)
```

### Data flow step by step

1. **Rust Engine** ingests 1Hz ticks via WebSocket → publishes to NATS + persists to QuestDB
2. **Python ML** consumes ticks → computes 84 features → runs LGBM+LSTM+GARCH ensemble → HMM regime → causal analysis → publishes composite signal
3. **Trading Agent** consumes signal → Risk Guardian veto → Kelly sizing → Claude AI validation → order execution
4. **Next.js Frontend** receives decisions via Server-Sent Events (NATS → server → browser)

---

## Services & Ports

| Service | Port | Role |
|---------|------|------|
| `nextjs-frontend` | 3005 | Web UI, auth, billing, SSE streams |
| `nats` | 4222 (client), 8223 (WS) | Message bus between all services |
| `questdb` | 9010 (HTTP), 8813 (PG), 9019 (ILP) | Time-series: ticks, signals, features |
| `postgres` | 5433 | Relational: users, orders, config |
| `redis` | 6381 | Rate limiting (sliding window) |
| `rust-engine` | 8085 | WebSocket ingestion + anomaly detection |
| `python-ml` | 8086 | Feature engineering + ML models |
| `trading-agent` | 8090 | Risk + Claude + order execution |
| `pg_backup` | — | Daily pg_dump, 7-day retention |

### NATS subjects

| Subject | Description |
|---------|-------------|
| `market.tick.{EXCHANGE}.{SYMBOL}` | 1Hz price ticks |
| `market.snapshot` | All symbols aggregated every 5s |
| `market.anomaly.{EXCHANGE}.{SYMBOL}` | Price gaps >1%, volume spikes >3σ |
| `ml.signals.composite` | Ensemble predictions + 84 features + regime |
| `ml.research.brief` | Alert level + sentiment summary |
| `agent.decisions.{userId}` | Per-user trade decisions (auth-gated) |
| `agent.status.{userId}` | Agent runtime status (auth-gated) |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Rust 1.85+ (for local engine development)
- Node.js 20+ (for frontend development)
- Python 3.11+ (for ML/agent development)

### 1. Configure environment

```bash
cp .env.example .env
# Fill in your API keys (Alpaca, Finnhub, Anthropic, Stripe, etc.)
```

### 2. Start all services

```bash
docker-compose up -d
```

### 3. Open the dashboard

Navigate to [http://localhost:3005](http://localhost:3005)

### 4. Tear down

```bash
docker-compose down -v   # -v destroys volumes (data loss)
```

---

## Development

### Rust Engine

```bash
cd rust-engine
cargo build --release
cargo test --release
RUST_LOG=info cargo run --release
```

> Requires Rust 1.85+. The `time` crate is pinned to 0.3.36 — do not upgrade it.

### Python ML

```bash
# From repo root — uses shared .venv
.venv/Scripts/python -m pytest python-ml/tests/ -v
.venv/Scripts/python -m src.main              # Run service
.venv/Scripts/python -m src.backtesting --symbol AAPL --strategy nexquant
```

### Trading Agent

```bash
.venv/Scripts/python -m pytest trading-agent/tests/ -v
.venv/Scripts/python -m src.main
```

### Next.js Frontend

```bash
cd nextjs-frontend
npm ci
npx prisma generate    # Required after schema changes
npm run dev            # → http://localhost:3005
npm run build          # Must pass before merging
npm run lint
```

---

## Key Features

### ML Ensemble (3 models + meta-learner)

| Model | Role |
|-------|------|
| **LGBMPredictor** | Self-labeling gradient boosting, retrains every 500 samples |
| **LSTMPredictor** | 2-layer 64-unit LSTM, lazy PyTorch import |
| **VolatilityPredictor** | GARCH(1,1) + HAR-RV fallback, annualized 1Hz vol |
| **EnsemblePredictor** | LogisticRegression meta-learner; disagreement rule: if confidence < 0.6 → HOLD |

### 84 Engineered Features

| Module | Count | Examples |
|--------|-------|---------|
| Technical | 46 | RSI(7,14,28), MACD, Bollinger Bands, ATR, OBV, ADX, Stochastic, Williams %R, CCI, MFI, EMA(5,10,20,50), SMA, CMF, Keltner, Donchian, Aroon |
| Microstructure | 20 | VWAP, realized vol, Parkinson, Garman-Klass, Amihud illiquidity, autocorrelation |
| Cross-asset | ~10 | Correlation + beta vs SPY/BTC/TLT/QQQ/GLD |
| Momentum | ~8 | Returns (5 horizons), z-scores, ROC, trend R² |

### 5-State HMM Regime Detection

`BULL_QUIET` · `BULL_VOLATILE` · `SIDEWAYS` · `BEAR_QUIET` · `BEAR_VOLATILE`

Falls back to volatility threshold when fewer than 200 observations.

### Risk Guardian (veto layer — runs before everything)

1. **Daily decision cap** — max 50 actual trade decisions per day
2. **DANGER alert** — blocks BUY when Market Sentinel detects anomaly
3. **Volatile regime cap** — max 2 open positions in VOLATILE regimes
4. **Concentration limit** — rejects if single position would exceed 40% of portfolio

### Claude AI Decision Layer

Every non-HOLD decision is evaluated by Claude before execution:
- Receives: signal, regime, causal relationships, risk profile, open positions, account state
- Returns: APPROVE / REJECT / REDUCE + reasoning
- Threshold: confidence > 0.65 AND expected return ≥ 0.25%

### Kelly Criterion Sizing

`kelly_fraction = half_kelly_base × regime_multiplier × (1 - concentration_penalty)`

- **Half-Kelly:** Conservative base (0.25 of signal Kelly)
- **Regime multiplier:** 1.0 for BULL, 0.7 for BEAR/SIDEWAYS, 0.5 for VOLATILE
- **Concentration penalty:** Reduces size if symbol already overweight in portfolio

---

## Environment Variables

See [.env.example](.env.example) for the full list. Key variables:

```bash
# AI
ANTHROPIC_API_KEY=...

# Market data
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
FINNHUB_API_KEY=...
MARKET_DATA_SOURCE=mock   # mock | alpaca | finnhub

# Database
POSTGRES_PASSWORD=nexquant_dev
ENCRYPTION_KEY=...        # For encrypting broker credentials

# Frontend
NEXTAUTH_SECRET=...
STRIPE_SECRET_KEY=...
STRIPE_PRO_PRICE_ID=...
STRIPE_WEBHOOK_SECRET=...

# Agent
CLAUDE_ENABLED=true
CLAUDE_CONFIDENCE_THRESHOLD=0.65
ALERT_WEBHOOK_URL=...     # Discord/Slack webhook (optional)
```

---

## Tech Stack

| Service | Core Technologies |
|---------|------------------|
| **Rust Engine** | tokio, async-nats, axum, tokio-tungstenite |
| **Python ML** | numpy, pandas, lightgbm, torch, arch, hmmlearn, statsmodels, ta |
| **Trading Agent** | asyncpg, anthropic SDK, httpx, cryptography, structlog |
| **Next.js Frontend** | Next.js 14, Prisma, NextAuth, Stripe, TailwindCSS, Recharts |
| **Infrastructure** | NATS (JetStream), QuestDB, PostgreSQL, Redis, Docker Compose |

---

## Database Schema

### PostgreSQL (Prisma)

- **User** — Auth, subscription status, grace period
- **BrokerConnection** — Encrypted API keys (Alpaca / Bitget)
- **AgentConfig** — Strategy parameters per user (maxPos, dailyLoss, aggressiveness)
- **RiskProfile** — 6-dimension questionnaire → CONSERVATIVE / MODERATE / AGGRESSIVE / SPECULATIVE
- **Order** — Trade execution log with entry/exit prices
- **ClaudeDecision** — Full reasoning trace per decision
- **AuditLog** — Security audit trail

### QuestDB (time-series)

- **market_data** — OHLCV ticks at 1Hz
- **ml_signals** — Composite signals (signal, confidence, regime, causal_alpha)
- **feature_store** — 84 engineered features per tick
- **causal_graph** — Directed causal relationships (Granger F-stat, Transfer Entropy)

---

## CI/CD

GitHub Actions runs on every push to `main`/`master` and on all PRs:

| Job | What it tests |
|----|--------------|
| `python-ml (150 tests)` | Feature engineering, ML ensemble, backtesting, model lifecycle |
| `trading-agent (97 tests)` | Risk Guardian, decision engine, Claude layer, multi-agent |
| `rust-engine (build + test)` | Cargo build + test |
| `nextjs-frontend (build)` | Prisma generate + Next.js production build |

Security review via `claude-code-security-review` runs automatically on all PRs.

---

## Known Gotchas

- **FeatureStore warm-up** — needs ~20 ticks before returning non-empty features
- **1Hz annualization** — factor ≈ 2784; `vol=0.001/tick` → 278% annualized (HIGH_VOL)
- **sys.path clash** — both `python-ml` and `trading-agent` define `src/`; add `python-ml/src/` directly to sys.path when cross-importing
- **prisma generate** — must run after any schema change or the build fails
- **QuestDB healthcheck** — image has no curl/wget; use `bash -c 'echo > /dev/tcp/localhost/9000'`
- **Rust `time` crate** — pinned to 0.3.36; do not upgrade (breaks on Rust <1.88)

---

## License

Private — All rights reserved.

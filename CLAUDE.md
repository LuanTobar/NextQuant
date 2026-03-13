# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Full Stack
```bash
docker-compose up -d          # Start all 9 services
docker-compose logs -f rust-engine
docker-compose down -v        # Tear down (destroys volumes)
```

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
# From repo root (shared .venv)
.venv/Scripts/python -m pytest python-ml/tests/ -v
.venv/Scripts/python -m pytest python-ml/tests/test_features.py -v  # single module
.venv/Scripts/python -m src.main                                      # run service
.venv/Scripts/python -m src.backtesting --symbol AAPL --strategy nexquant
pip install pytest  # if missing from .venv
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
npm run dev        # dev server → http://localhost:3005
npm run build      # production build (must pass before merging)
npm run lint
npx prisma migrate dev
npx prisma generate  # required after schema changes
```

## Architecture

**Data Pipeline**
```
Market Sources (Alpaca/Finnhub/Bitget/Mock)
  → Rust Engine  (WebSocket ingestion, anomaly detection)
  → NATS         (market.tick.*, market.snapshot, market.anomaly.*)
  → Python ML    (84 features, LGBM+LSTM+GARCH ensemble, HMM regime, causal analysis)
  → NATS         (ml.signals.composite, ml.research.brief)
  → Trading Agent (Risk Guardian → Kelly sizing → Claude decision layer → execution)
  → PostgreSQL   (orders, audit) + QuestDB (ticks, signals)
  → Next.js      (SSE /api/stream/* → browser)
```

**Services & Ports**
| Service        | Host Port | Health |
|----------------|-----------|--------|
| nextjs-frontend | 3005     | —      |
| nats            | 4222 (client), 8223 (WS) | 8245/healthz |
| questdb         | 9010 (HTTP), 8813 (PG), 9019 (ILP) | — |
| postgres        | 5433     | —      |
| redis           | 6381     | —      |
| rust-engine     | 8085     | /health |
| python-ml       | 8086     | /health |
| trading-agent   | 8090     | /health |

**NATS Subjects**
- `market.tick.{EXCHANGE}.{SYMBOL}` — 1Hz ticks
- `market.snapshot` — all symbols, every 5s
- `market.anomaly.{EXCHANGE}.{SYMBOL}` — price gaps >1%, volume spikes >3σ
- `ml.signals.composite` — ensemble predictions + features per symbol
- `ml.research.brief` — alert level + market sentiment
- `agent.decisions.{userId}` — per-user trade decisions (auth-gated SSE)
- `agent.status.{userId}` — agent status (auth-gated SSE)

## Key Design Decisions

- **NATS not PyO3**: Rust↔Python via message bus to avoid GIL latency spikes (10–80ms)
- **HybridSource**: Wraps Alpaca/Finnhub/Bitget with auto-Mock fallback when markets are closed; controlled by `MARKET_DATA_SOURCE` env var
- **Ensemble stacking**: LGBMPredictor + LSTMPredictor + VolatilityPredictor → meta-learner (LogisticRegression). Disagreement rule: if confidence < 0.6 → HOLD
- **5-state HMM**: BULL_QUIET, BULL_VOLATILE, SIDEWAYS, BEAR_QUIET, BEAR_VOLATILE. Falls back to vol-threshold when < 200 observations
- **Causal pipeline**: Granger F-test + transfer entropy (lag-1 directed). Background analysis every 50 ticks
- **Model persistence**: joblib + `registry.json` versioning in `/app/models` (Docker volume `ml-models`). Checkpoint every 10min. Drift alert if `rolling_accuracy(n=100) < 0.48`
- **Kelly sizing**: Half-Kelly per signal, regime-weighted, concentration-penalized
- **Risk Guardian veto**: blocks DANGER alerts; caps volatile positions at 2%, concentration at 40%, daily loss at 50%
- **SSE not WebSocket for free tier**: NATS → Next.js server → browser (browser never connects to NATS directly)
- **Redis rate limiting**: sliding window ZADD/ZCOUNT; falls back to in-memory if Redis unavailable

## QuestDB Tables
- `market_data` — OHLCV ticks
- `ml_signals` — composite ML signals
- `feature_store` — 84 engineered features
- `causal_graph` — directed causal relationships

## PostgreSQL (Prisma)
Key models: `User`, `BrokerConnection` (encrypted keys), `AgentConfig`, `RiskProfile`, `Order`, `ClaudeDecision`, `AuditLog`

## Known Gotchas

- **FeatureStore warm-up**: ~20 ticks before returning non-empty features. Tests counting LGBM labels must subtract ~20 from expected_min.
- **1Hz annualization**: `sqrt(252 × 6.5 × 3600) ≈ 2784`. `vol=0.001/tick → 278%` annualized (HIGH_VOL). For "low vol" tests use `vol ≤ 0.00005`.
- **HMM cross-model comparison**: two HMMs on different vol scales learn relative states; use OR assertion (prob ordering OR regime label check).
- **Transfer entropy**: lag-1 only — measures `X_{t-1} → Y_t`, not contemporaneous. Tests must use lagged causal structure.
- **Backtest commission**: `entry_total_cost = cash * size` exactly. Guard: `trade_value = cash * size / (1 + commission)`.
- **QuestDB healthcheck**: image has no curl/wget — use `bash -c 'echo > /dev/tcp/localhost/9000'`.
- **Pylance false positives**: IDE not configured for `.venv`; code runs correctly via `.venv/Scripts/python.exe`.
- **sys.path clash**: both `python-ml` and `trading-agent` define a `src/` package. Add `python-ml/src/` directly (not `python-ml/`) to `sys.path` when cross-importing.
- **`prisma generate`**: must run after any schema change or the build will fail.

## AI Best Practices

> **Regla estricta de contexto**: Al trabajar en un feature, restringe la lectura de archivos y el contexto exclusivamente a la carpeta del microservicio correspondiente, a menos que se requiera modificar interfaces compartidas entre servicios.

### Scope por tarea

| Si la tarea involucra... | Leer únicamente... |
|--------------------------|-------------------|
| UI, API routes, auth, billing | `nextjs-frontend/` |
| Feature engineering, ML models, backtesting | `python-ml/` |
| Decisiones de trading, brokers, ejecución, Claude layer | `trading-agent/` |
| Ingestión de datos, anomaly detection, WebSocket | `rust-engine/` |
| NATS config, QuestDB config | `infrastructure/` |

### Interfaces compartidas (leer ambos servicios si se modifican)

- **NATS message schemas**: definidos en `python-ml/src/research_brief.py`, consumidos en `nextjs-frontend/src/hooks/useResearchStream.ts` y `trading-agent/src/agent_loop.py`
- **QuestDB table schemas**: definidos en `python-ml/src/features/store.py`, consultados en `nextjs-frontend/src/lib/questdb-client.ts` y `rust-engine/src/storage/questdb.rs`
- **Prisma schema** (`nextjs-frontend/prisma/schema.prisma`): también consumido por `trading-agent/src/db.py` vía asyncpg
- **Encryption format**: `nextjs-frontend/src/lib/encryption.ts` ↔ `trading-agent/src/encryption.py` (deben mantenerse en sync)
- **Broker credential `extra` JSON**: `nextjs-frontend/src/app/api/broker/route.ts` → `trading-agent/src/brokers/__init__.py`

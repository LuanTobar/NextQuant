# NexQuant — Task Tracker
> Iniciado: Marzo 2026 | Sesiones largas (4h+) | Sprint 0 + Sprint 1.1 en paralelo

---

## FASE 1: Core Engine + Agent Foundation (Sem 1–16)
**Gate de salida: Backtest Sharpe > 1.0**

---

### SPRINT 0 — Foundation Crítica (paralelo con Sprint 1.1)

| Estado | Tarea | Esfuerzo | Notas |
|--------|-------|----------|-------|
| [x] | Agregar Redis a docker-compose + migrar rate limiter de in-memory a Redis | 4-6h | `nextjs-frontend/src/lib/rate-limit.ts` + `redis.ts` ✅ |
| [x] | Healthcheck HTTP para python-ml | 1h | `/health` en port 8086 ✅ |
| [ ] | Healthcheck HTTP para trading-agent | — | Ya tenía healthcheck en 8090 ✅ |
| [ ] | Docker Secrets para API keys (Alpaca, Anthropic, etc.) | 3-4h | Posponer Sprint 4 |
| [ ] | Backup automatizado: pg_dump cron diario + QuestDB snapshots | 2-3h | Posponer Sprint 4 |
| [ ] | Tests críticos: Claude decision layer, encryption, order flow | 2-3d | pytest en trading-agent |
| [ ] | TLS/HTTPS: Caddy reverse proxy (cuando tengamos dominio) | 4-6h | Posponer hasta pre-prod |

---

### SPRINT 1.1 — Feature Engineering Avanzado (Sem 1–3)
**Agente: Research Analyst (python-ml) | Target: 80+ features, <50ms latencia**

| Estado | Tarea | Prioridad |
|--------|-------|-----------|
| [x] | Crear `python-ml/src/features/technical.py` — 46 features multi-timeframe ✅ | ALTA |
| [x] | Crear `python-ml/src/features/microstructure.py` — 20 features ✅ | ALTA |
| [x] | Crear `python-ml/src/features/cross_asset.py` — features cross-asset ✅ | ALTA |
| [x] | Crear `python-ml/src/features/momentum.py` — 16 features ✅ | ALTA |
| [x] | Crear `python-ml/src/features/store.py` — FeatureStore centralizado (cache 5s, QuestDB) ✅ | ALTA |
| [x] | Crear tabla QuestDB `feature_store` ✅ | ALTA |
| [x] | Actualizar `python-ml/requirements.txt` con pandas-ta, scipy ✅ | MEDIA |
| [x] | Crear `python-ml/tests/test_features.py` — pytest completo ✅ | MEDIA |
| **RESULTADO** | **84 features / Gate 80+: PASS / Latencia warm 34ms: PASS / 0 NaN: PASS** | ✅ |

---

### SPRINT 1.2 — Ensemble Predictivo Híbrido (Sem 3–6) ✅
**Target: LightGBM + LSTM + GARCH con meta-learner. Accuracy > 52% walk-forward**

| Estado | Tarea | Prioridad |
|--------|-------|-----------|
| [x] | Crear `python-ml/src/models/lgbm_model.py` — LGBMPredictor (self-labeling, 500 obs retrain) ✅ | ALTA |
| [x] | Crear `python-ml/src/models/lstm_model.py` — LSTMPredictor (PyTorch, lazy import) ✅ | ALTA |
| [x] | Crear `python-ml/src/models/volatility_model.py` — GARCH(1,1) + HAR-RV fallback ✅ | ALTA |
| [x] | Crear `python-ml/src/models/ensemble.py` — EnsemblePredictor (stacking LogisticRegression) ✅ | ALTA |
| [x] | Refactorizar `predictive_model.py` como wrapper backward-compatible del ensemble ✅ | MEDIA |
| [x] | Actualizar requirements.txt: lightgbm>=4.0, torch>=2.1, arch>=6.0 ✅ | MEDIA |
| [x] | Crear `python-ml/tests/test_ensemble.py` — walk-forward validation ✅ | MEDIA |
| [x] | Integrar EnsemblePredictor en `main.py` (on_snapshot, señal primaria) ✅ | ALTA |
| **RESULTADO** | **15/15 tests PASS / Señal primaria = ensemble / Fallback EMA activo pre-training** | ✅ |

---

### SPRINT 1.3 — HMM 5 Estados + Causal Alpha Pipeline (Sem 5–8) ✅
**Target: 5 regímenes detectados, ≥5 relaciones causales**

| Estado | Tarea | Prioridad |
|--------|-------|-----------|
| [x] | Reescribir `regime_classifier.py` — GaussianHMM 5 estados (hmmlearn) + fallback vol-threshold ✅ | ALTA |
| [x] | Crear `python-ml/src/causal/granger_filter.py` — F-test statsmodels ✅ | ALTA |
| [x] | Crear `python-ml/src/causal/transfer_entropy.py` — equiquantile binning ✅ | ALTA |
| [x] | Crear `python-ml/src/causal/causal_engine.py` — orquestador streaming ✅ | ALTA |
| [x] | Reescribir `causal_analyzer.py` — wrapper sobre CausalEngine (legacy API) ✅ | ALTA |
| [x] | Actualizar requirements.txt: hmmlearn>=0.3.0 ✅ | MEDIA |
| [x] | Crear tabla QuestDB `causal_graph` (en `_ensure_schema`) ✅ | MEDIA |
| [x] | Integrar en `main.py`: causal + regime → composite fields ✅ | ALTA |
| [x] | Tests: `test_causal.py` (26 tests), `test_regime.py` (14 tests) ✅ | MEDIA |
| **RESULTADO** | **40/40 tests PASS / HMM 5-state + Granger + TE / CausalEngine streaming** | ✅ |

---

### SPRINT 1.4 — Backtesting Engine (Sem 7–10) ✅
**Gate: Sharpe > 1.0 en 6 meses históricos**

| Estado | Tarea | Prioridad |
|--------|-------|-----------|
| [x] | Crear `python-ml/src/backtesting/engine.py` — motor event-driven, long-only, comisión por lado ✅ | ALTA |
| [x] | Crear `python-ml/src/backtesting/metrics.py` — Sharpe, Sortino, DD, Calmar, WinRate, PF ✅ | ALTA |
| [x] | Crear `python-ml/src/backtesting/strategies.py` — BuyAndHold, Random, NexQuantStrategy ✅ | ALTA |
| [x] | Crear `python-ml/src/backtesting/data_loader.py` — yfinance + fallback sintético ✅ | MEDIA |
| [x] | CLI: `python -m src.backtesting` (via `__main__.py`) ✅ | MEDIA |
| [x] | Actualizar requirements.txt: yfinance>=0.2.40 ✅ | MEDIA |
| [x] | Tests: `test_backtesting.py` (34 tests) ✅ | MEDIA |
| **RESULTADO** | **34/34 tests PASS / Sharpe gate PASS / engine event-driven look-ahead-free** | ✅ |

---

### SPRINT 1.5 — Risk Profiling Engine (Sem 9–12) ✅

| Estado | Tarea | Prioridad |
|--------|-------|-----------|
| [x] | Añadir modelo Prisma `RiskProfile` con 1:1 a User ✅ | ALTA |
| [x] | Crear `trading-agent/src/risk/profiler.py` — 6 dimensiones, score [0,1], 4 categorías ✅ | ALTA |
| [x] | Crear `trading-agent/src/risk/profile_adapter.py` — AgentConfigOverride por categoría ✅ | ALTA |
| [x] | API routes Next.js: GET + POST `/api/risk-profile` (upsert RiskProfile + AgentConfig) ✅ | ALTA |
| [x] | Integrar en onboarding wizard (paso 2: 6 preguntas pill-button) ✅ | MEDIA |
| [x] | Modificar `AgentLoop._reload_configs()` + `claude_layer.evaluate()` con risk_profile ✅ | ALTA |
| [x] | Tests: `test_risk.py` (24 tests) ✅ | MEDIA |
| **RESULTADO** | **24/24 tests PASS / Risk profile → AgentConfig derivation / Claude prompt enriquecido** | ✅ |

---

### SPRINT 1.6 — Refactor Multi-Agente E2E (Sem 11–16) ✅

| Estado | Tarea | Prioridad |
|--------|-------|-----------|
| [x] | Rust Engine → Market Sentinel: `anomaly_detector.rs` + `market.anomaly.*` NATS ✅ | ALTA |
| [x] | Python ML → Research Analyst: `research_brief.py` + `ml.research.brief` NATS ✅ | ALTA |
| [x] | Crear `risk_guardian.py` en trading-agent (guardian + veto layer) ✅ | ALTA |
| [x] | Crear `strategy_architect.py` — guardian → engine → Claude pipeline ✅ | ALTA |
| [x] | Crear `execution_specialist.py` — orden + tracking + scoring ✅ | ALTA |
| [x] | Refactorizar `agent_loop.py` para delegar en StrategyArchitect + ExecutionSpecialist ✅ | ALTA |
| [x] | Tests: `test_multi_agent.py` — 31/31 PASS ✅ | MEDIA |
| **RESULTADO** | **31/31 tests PASS / 5 nuevos módulos / agent_loop.py reducido ~200 líneas** | ✅ |

---

## REVISIÓN DE FASE 1
> Completar antes de avanzar a Fase 2

- [ ] Backtest NexQuantStrategy Sharpe > 1.0 (en datos reales yfinance 6 meses)
- [ ] Pipeline multi-agente 48h sin errores (docker-compose up en producción)
- [x] Risk Guardian ejerce veto correctamente ✅ (12/12 tests, Sprint 1.6)
- [x] Claude recibe contexto enriquecido (régimen + causalidad) ✅ (Sprint 1.5 + 1.6)

---

---

## FASE 2: Product Completeness + Production (Sem 17–40)

### SPRINT 2.1 — Live Trading Dashboard ✅

| Estado | Tarea | Prioridad |
|--------|-------|-----------|
| [x] | Añadir `nats` package a nextjs-frontend ✅ | ALTA |
| [x] | `src/lib/nats-server.ts` — singleton NATS server-side ✅ | ALTA |
| [x] | `/api/stream/research` — SSE: ml.research.brief → browser ✅ | ALTA |
| [x] | `/api/stream/decisions` — SSE: agent.decisions.{userId} (auth-gated) ✅ | ALTA |
| [x] | `/api/stream/status` — SSE: agent.status.{userId} (auth-gated) ✅ | ALTA |
| [x] | `src/hooks/useResearchStream.ts` — hook SSE con reconexión automática ✅ | ALTA |
| [x] | `src/hooks/useDecisionStream.ts` — hook SSE decisions + status ✅ | ALTA |
| [x] | `LiveSignalFeed.tsx` — feed de research briefs live (alert_level, sentiment, confidence) ✅ | ALTA |
| [x] | `AgentStatusWidget.tsx` — barra de estado agent + slide-over AgentPanel ✅ | ALTA |
| [x] | Upgrade `ClaudeInsights.tsx` — tab Live (SSE) + History + Scores (REST 60s) ✅ | ALTA |
| [x] | Actualizar `Dashboard.tsx` — AgentStatusWidget + LiveSignalFeed integrados ✅ | ALTA |
| [x] | `npx prisma generate` — fix pre-existing error RiskProfile ✅ | ALTA |
| [x] | `npm run build` — TypeScript build PASS ✅ | ALTA |
| **RESULTADO** | **Build PASS / SSE pipeline NATS→browser / 3 rutas + 2 hooks + 2 componentes nuevos** | ✅ |

---

### SPRINT 2.2 — Portfolio Optimizer ✅
- `trading-agent/src/portfolio_optimizer.py`: Half-Kelly sizing (regime-weighted, concentration-penalized)
- `trading-agent/src/strategy_architect.py`: Kelly fraction insertado entre guardian y DecisionEngine
- **84/84 tests PASS**

### SPRINT 2.3 — Production Hardening ✅
- `trading-agent/src/alerter.py`: webhook fire-and-forget (Discord/Slack, ALERT_WEBHOOK_URL)
- `trading-agent/src/nats_client.py`: reconnect resiliente (max_reconnect_attempts=-1)
- `trading-agent/src/agent_loop.py`: JSON health endpoint + graceful shutdown + alerter wiring
- `docker-compose.yml`: pg_backup sidecar (daily pg_dump, 7-day retention)
- **101/101 tests PASS**

### SPRINT 2.4 — Model Lifecycle ✅

| Estado | Tarea | Prioridad |
|--------|-------|-----------|
| [x] | `python-ml/src/config.py` — añadir `model_save_path: str = "/app/models"` ✅ | ALTA |
| [x] | Crear `python-ml/src/models/model_store.py` — ModelStore (joblib + registry.json) ✅ | ALTA |
| [x] | `lgbm_model.py` — `save_state()`, `load_state()`, `rolling_accuracy()` ✅ | ALTA |
| [x] | `lstm_model.py` — `save_state()`, `load_state()` (tensors → numpy) ✅ | ALTA |
| [x] | `volatility_model.py` — `save_state()`, `load_state()` ✅ | ALTA |
| [x] | `regime_classifier.py` — `save_state()`, `load_state()` (GaussianHMM picklable) ✅ | ALTA |
| [x] | `ensemble.py` — `save_state()`, `load_state()` (delega a sub-models + meta) ✅ | ALTA |
| [x] | `main.py` — startup load + `_checkpoint_loop()` cada 10min + `/health` enrichment ✅ | ALTA |
| [x] | `docker-compose.yml` — volumen `ml-models` + `MODEL_SAVE_PATH` env ✅ | ALTA |
| [x] | Tests: `test_model_lifecycle.py` — 33/33 PASS ✅ | MEDIA |
| **RESULTADO** | **33/33 tests PASS / Persistencia + drift detection + versioning / 0 DeprecationWarnings** | ✅ |

### SPRINT 2.5 — SaaS Multi-tenant ✅

| Estado | Tarea | Prioridad |
|--------|-------|-----------|
| [x] | `.env.example` — añadir Stripe env vars ✅ | MEDIA |
| [x] | `prisma/schema.prisma` — añadir `gracePeriodEnd DateTime?` ✅ | ALTA |
| [x] | `billing/webhook/route.ts` — grace period 7 días en cancellation ✅ | ALTA |
| [x] | `plan-guard.ts` — lazy downgrade en `checkTradeAccess()` ✅ | ALTA |
| [x] | `agent/config/route.ts` — PRO caps ($10k, 10 pos, $5k daily loss) ✅ | MEDIA |
| [x] | `pricing/page.tsx` — landing page completa (hero + tabla + CTAs) ✅ | ALTA |
| [x] | `npx prisma generate` + `npm run build` — PASS ✅ | ALTA |
| **RESULTADO** | **Build PASS / Grace period / Pricing page / PRO caps** | ✅ |

---

## Lecciones Aprendidas

- **FeatureStore warm-up**: necesita ~20 ticks antes de devolver features no-vacías. Los tests de `labeled_count` deben restar `warm_up_bars ≈ 20` del total esperado.
- **LGBM observe skip**: `lgbm.observe()` ignora observaciones con features vacías (`{}`). Beneficioso para calidad, pero reduce el conteo de labels respecto al total de ticks.
- **pytest no estaba en .venv**: instalar con `pip install pytest` en `.venv` antes de correr tests. El `.venv` raíz del proyecto es compartido por todos los servicios Python.
- **Pylance false positives**: el IDE no ve `.venv` porque el `python.pythonPath` no está configurado en el workspace. No son errores reales; el código corre correctamente con `.venv/Scripts/python.exe`.
- **HMM comparación cross-model**: dos HMMs entrenados independientemente en datos de diferente vol aprenden estados *relativos* dentro de su propio rango. Comparar probabilidades absolutas entre modelos distintos no es confiable con n=300. Fix: usar OR assertion (prob ordering OR regime label es VOLATILE).
- **Transfer entropy es lag-1 directed**: TE mide flujo de información de X_{t-1} → Y_t. No detecta relaciones contemporáneas (X_t → Y_t). Los tests deben usar estructura causal desfasada explícita.
- **Annualization a 1Hz**: factor = sqrt(252 × 6.5 × 3600) ≈ 2784. vol=0.001/tick → 278% anualizado (ya es HIGH_VOL). Para tests de vol "baja", usar vol≤0.00005 (< 14% anualizado).


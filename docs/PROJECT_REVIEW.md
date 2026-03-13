# NexQuant — Technical Review & Architecture Document

**Fecha**: 8 de febrero de 2026
**Versión**: 1.0
**Tipo de documento**: Review técnico para evaluación de proyecto
**Audiencia**: Project Manager Full-Stack / Tech Lead

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura General del Sistema](#2-arquitectura-general-del-sistema)
3. [Infraestructura y Despliegue](#3-infraestructura-y-despliegue)
4. [Servicio 1: Rust Engine — Pipeline de Datos de Mercado](#4-servicio-1-rust-engine--pipeline-de-datos-de-mercado)
5. [Servicio 2: Python ML — Pipeline de Machine Learning](#5-servicio-2-python-ml--pipeline-de-machine-learning)
6. [Servicio 3: Trading Agent — Ejecución Autónoma + Claude Decision Layer](#6-servicio-3-trading-agent--ejecución-autónoma--claude-decision-layer)
7. [Servicio 4: Next.js Frontend — Aplicación Web SaaS](#7-servicio-4-nextjs-frontend--aplicación-web-saas)
8. [Flujo End-to-End: Del Dato de Mercado a la Ejecución del Trade](#8-flujo-end-to-end-del-dato-de-mercado-a-la-ejecución-del-trade)
9. [Sistemas Externos e Integraciones](#9-sistemas-externos-e-integraciones)
10. [Seguridad](#10-seguridad)
11. [Esquema de Base de Datos](#11-esquema-de-base-de-datos)
12. [Evaluación: Puntos Positivos](#12-evaluación-puntos-positivos)
13. [Evaluación: Puntos Críticos y Débiles](#13-evaluación-puntos-críticos-y-débiles)
14. [Recomendaciones de Mejora para Lanzamiento](#14-recomendaciones-de-mejora-para-lanzamiento)
15. [Apéndices](#15-apéndices)

---

## 1. Resumen Ejecutivo

**NexQuant** es una plataforma SaaS de trading algorítmico que combina datos de mercado en tiempo real, machine learning con inferencia causal, y una capa de validación inteligente basada en Claude AI (Anthropic) para ejecutar operaciones de forma autónoma en múltiples mercados (US Equities, Crypto, LSE, BME, TSE).

### Stack Tecnológico Principal

| Capa | Tecnología | Lenguaje |
|------|-----------|----------|
| Ingesta de datos | Tokio + WebSocket + Axum | Rust |
| Message Bus | NATS JetStream | — |
| Time-Series DB | QuestDB 7.3.10 | SQL |
| Application DB | PostgreSQL 16 | SQL |
| Machine Learning | DoWhy + scikit-learn + statsmodels | Python 3.12 |
| Trading Agent | asyncpg + httpx + cryptography | Python 3.12 |
| AI Decision Layer | Claude Sonnet 4 (Anthropic) | — |
| Frontend / API | Next.js 14 + Prisma + NextAuth | TypeScript |
| UI | Tailwind CSS + Recharts + Framer Motion | TypeScript |
| Orquestación | Docker Compose (7 servicios) | YAML |

### Métricas del Proyecto

| Métrica | Valor |
|---------|-------|
| Servicios Docker | 7 |
| API Routes (Next.js) | 29 |
| Componentes React | 14+ |
| Páginas (App Router) | 13 |
| Modelos Prisma | 7 |
| Mercados soportados | 5 (US, Crypto, LSE, BME, TSE) |
| Symbols activos | 25 |
| Brokers integrados | 2 (Alpaca, Bitget) |

---

## 2. Arquitectura General del Sistema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FLUJO DE DATOS END-TO-END                          │
│                                                                             │
│  ┌──────────────┐     ┌──────┐     ┌───────────┐     ┌──────────────────┐  │
│  │  Rust Engine  │────▶│ NATS │────▶│ Python ML │────▶│  Trading Agent   │  │
│  │  (Data Feed)  │     │  Bus │     │ (Signals) │     │ (Claude + Exec)  │  │
│  └──────┬───────┘     └──┬───┘     └─────┬─────┘     └────────┬─────────┘  │
│         │                │               │                     │            │
│         ▼                │               ▼                     ▼            │
│    ┌─────────┐           │         ┌─────────┐          ┌───────────┐      │
│    │ QuestDB │◀──────────┘         │ QuestDB │          │PostgreSQL │      │
│    │(ticks)  │                     │(signals)│          │ (orders)  │      │
│    └────┬────┘                     └────┬────┘          └─────┬─────┘      │
│         │                               │                     │            │
│         └────────────────┬──────────────┘                     │            │
│                          ▼                                    │            │
│                   ┌─────────────┐                             │            │
│                   │   Next.js   │◀────────────────────────────┘            │
│                   │  Frontend   │                                          │
│                   └─────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Patrón de Comunicación

- **Inter-servicio**: NATS JetStream (pub/sub asíncrono, mensajería persistente)
- **Almacenamiento time-series**: QuestDB (ingesta de alta velocidad, SQL analytics)
- **Almacenamiento relacional**: PostgreSQL 16 con Prisma ORM
- **Browser ↔ NATS**: WebSocket en puerto 8223 (real-time updates al frontend)

### Subjects NATS

| Subject | Publisher | Consumer | Frecuencia |
|---------|-----------|----------|------------|
| `market.tick.{EXCHANGE}.{SYMBOL}` | Rust Engine | Python ML | 1Hz por symbol |
| `market.snapshot` | Rust Engine | Python ML, Frontend | 5s |
| `ml.signals.composite` | Python ML | Trading Agent | 5s por symbol |
| `agent.decisions.{userId}` | Trading Agent | Frontend | Por evento |
| `agent.status.{userId}` | Trading Agent | Frontend | 30s |
| `agent.command.{userId}` | Frontend | Trading Agent | Por evento |

---

## 3. Infraestructura y Despliegue

### 3.1 Docker Compose — 7 Servicios

**Archivo**: `docker-compose.yml`

| Servicio | Imagen / Build | Puertos Expuestos | Healthcheck |
|----------|---------------|-------------------|-------------|
| **nats** | `nats:2.10-alpine` | 4222 (client), 8223 (WebSocket), 6222 (cluster) | HTTP :8245 |
| **questdb** | `questdb/questdb:7.3.10` | 9010 (HTTP), 9019 (InfluxDB LP), 8813 (PG wire) | TCP :9000 |
| **postgres** | `postgres:16-alpine` | 5433 (external) → 5432 (internal) | `pg_isready` |
| **rust-engine** | Build: `./rust-engine/Dockerfile` | 8085 (health) | HTTP :8080/health |
| **python-ml** | Build: `./python-ml/Dockerfile` | — | — |
| **trading-agent** | Build: `./trading-agent/Dockerfile` | 8090 (health) | HTTP :8090 |
| **nextjs-frontend** | Build: `./nextjs-frontend/Dockerfile` | 3005 (HTTP) | — |

### 3.2 Mapa de Puertos

Los puertos fueron desplazados deliberadamente para evitar conflictos con otros proyectos Docker corriendo simultáneamente:

```
Puerto 3005  →  Next.js (evita 3000-3002 ocupados por otros frontends)
Puerto 4222  →  NATS Client
Puerto 5433  →  PostgreSQL (evita 5434 de otro postgres)
Puerto 8085  →  Rust Engine Health
Puerto 8090  →  Trading Agent Health
Puerto 8223  →  NATS WebSocket (evita 8222 default)
Puerto 8813  →  QuestDB PG Wire
Puerto 9010  →  QuestDB HTTP Console (evita 9000 ocupado)
Puerto 9019  →  QuestDB InfluxDB Line Protocol
```

### 3.3 Volúmenes Persistentes

| Volumen | Servicio | Datos |
|---------|----------|-------|
| `questdb-data` | QuestDB | Time-series data (market_data, ml_signals, claude_decisions) |
| `postgres-data` | PostgreSQL | Datos de aplicación (users, orders, configs, etc.) |
| `nats-data` | NATS | JetStream persistent storage |

### 3.4 Configuración NATS JetStream

**Archivo**: `infrastructure/nats/nats.conf`

```conf
listen: 0.0.0.0:4222

jetstream {
  store_dir: "/data/jetstream"
  max_memory_store: 256MB
  max_file_store: 1GB
}

websocket {
  listen: "0.0.0.0:8222"
  no_tls: true
}

http_port: 8245
max_payload: 1MB
max_connections: 1024
```

- **Memory store**: 256MB para streams in-memory
- **File store**: 1GB para persistencia en disco
- **Max payload**: 1MB por mensaje (suficiente para snapshots de 25 symbols)
- **WebSocket**: Sin TLS para desarrollo (requiere TLS para producción)

### 3.5 Configuración QuestDB

**Archivo**: `infrastructure/questdb/server.conf`

```conf
http.enabled=true
http.bind.to=0.0.0.0:9000
pg.enabled=true
pg.net.bind.to=0.0.0.0:8812
line.tcp.enabled=true
line.tcp.net.bind.to=0.0.0.0:9009
cairo.commit.lag=1000
cairo.max.uncommitted.rows=10000
```

- **Commit lag**: 1000ms (agrupación de escrituras para throughput)
- **Max uncommitted rows**: 10000 (buffer antes de flush)
- **Tres protocolos habilitados**: HTTP API, PostgreSQL Wire, InfluxDB Line Protocol

### 3.6 Build Optimizations

**Rust Engine Dockerfile** — Multi-stage build con cache de dependencias:
1. Etapa 1: Crea `dummy main.rs`, compila dependencias
2. Etapa 2: Copia código real, `touch src/main.rs` para invalidar cache selectivamente
3. Resultado: Rebuilds ~10x más rápidos (solo recompila código del proyecto)

**Next.js Dockerfile** — Multi-stage con output standalone:
1. Etapa deps: `npm ci` (install dependencies)
2. Etapa build: `next build` (genera .next/standalone)
3. Etapa runtime: Solo node + standalone + static (imagen final ~200MB vs ~1.5GB)

---

## 4. Servicio 1: Rust Engine — Pipeline de Datos de Mercado

### 4.1 Propósito

Ingesta de datos de mercado en tiempo real desde múltiples exchanges y proveedores, normalización, almacenamiento en QuestDB, y distribución via NATS a consumidores downstream.

### 4.2 Stack Técnico

**Archivo principal**: `rust-engine/src/main.rs`
**Dependencias clave** (de `Cargo.toml`):

| Crate | Versión | Uso |
|-------|---------|-----|
| `tokio` | 1.x (full) | Async runtime |
| `async-nats` | 0.35 | NATS client |
| `reqwest` | 0.12 | HTTP client (QuestDB API) |
| `axum` | 0.7 | Health check HTTP server |
| `tokio-tungstenite` | 0.24 | WebSocket client (market data feeds) |
| `chrono` / `chrono-tz` | 0.4 / 0.10 | Timezone-aware market hours |
| `serde` / `serde_json` | 1.0 | JSON serialization |

**Build profile (release)**: `opt-level = 3`, `lto = true` (Link-Time Optimization para máximo rendimiento)

### 4.3 Arquitectura de Fuentes de Datos

```
                    ┌──────────────┐
                    │  HybridSource│ (auto-fallback when market closed)
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  Alpaca   │ │ Finnhub  │ │  Bitget  │
        │(US/IEX)  │ │(LSE/BME/ │ │ (Crypto) │
        │WebSocket │ │TSE) WS   │ │WebSocket │
        └──────────┘ └──────────┘ └──────────┘
              │            │            │
              └────────────┼────────────┘
                           ▼
                    ┌──────────────┐
                    │   MockSource │ (fallback: random walk simulator)
                    └──────────────┘
```

**Trait `DataSource`** (`src/market_data/source.rs`):
- Interface unificada para todas las fuentes
- Cada fuente implementa `connect()` y `subscribe()` → produce `MarketTick`

**`HybridSource`** (`src/market_data/hybrid_source.rs`):
- Wrapper que detecta horarios de mercado usando `chrono-tz`
- Si el mercado está cerrado: usa `MockSource` automáticamente
- Transición transparente al abrir/cerrar mercado

**Fuentes de datos implementadas**:

| Fuente | Archivo | Exchange | Protocolo | Mercados |
|--------|---------|----------|-----------|----------|
| `AlpacaSource` | `alpaca_source.rs` | US | WebSocket IEX | NYSE, NASDAQ |
| `FinnhubSource` | `finnhub_source.rs` | EU/Asia | WebSocket | LSE, BME, TSE |
| `BitgetSource` | `bitget_source.rs` | Crypto | WebSocket | Crypto 24/7 |
| `MockSource` | `mock_source.rs` | — | Random walk | Fallback |

### 4.4 Distribución de Datos

**`tokio::broadcast::channel`** con buffer de 4096:
- Un canal de broadcast permite múltiples consumers sin overhead
- Cada tick va a: NATS publisher + QuestDB writer + snapshot aggregator

**Flujo de publicación**:
1. Tick recibido del WebSocket → parse → `MarketTick`
2. Publish a `market.tick.{EXCHANGE}.{SYMBOL}` (1Hz por symbol)
3. Cada 5s: agregar snapshot de todos los symbols → `market.snapshot`
4. Escritura batch a QuestDB tabla `market_data` (batch size: 10)

### 4.5 Configuración Multi-Mercado

**Variable de entorno**: `MARKETS` (JSON array)

```json
[
  {"exchange": "CRYPTO", "provider": "bitget", "symbols": ["BTCUSDT", "ETHUSDT", ...]},
  {"exchange": "US", "provider": "alpaca", "symbols": ["AAPL", "GOOGL", ...]},
  {"exchange": "LSE", "provider": "finnhub", "symbols": ["VOD.L", "BP.L", ...]},
  {"exchange": "BME", "provider": "finnhub", "symbols": ["SAN.MC", "TEF.MC", ...]},
  {"exchange": "TSE", "provider": "finnhub", "symbols": ["7203.T", "6758.T", ...]}
]
```

### 4.6 Tabla QuestDB: `market_data`

```sql
CREATE TABLE IF NOT EXISTS market_data (
  timestamp TIMESTAMP,
  symbol    SYMBOL,
  exchange  SYMBOL,
  open      DOUBLE,
  high      DOUBLE,
  low       DOUBLE,
  close     DOUBLE,
  volume    DOUBLE
) TIMESTAMP(timestamp) PARTITION BY DAY;
```

- **Particionado por día**: Optimizado para queries con rango de fecha
- **Symbol type**: Columna indexada automáticamente por QuestDB (O(1) lookup)

### 4.7 Health Check

- Servidor Axum en `:8080/health`
- Retorna JSON con estado de cada componente (NATS, QuestDB, fuentes activas)
- Usado por Docker Compose para `depends_on: condition: service_healthy`

---

## 5. Servicio 2: Python ML — Pipeline de Machine Learning

### 5.1 Propósito

Procesar datos de mercado en tiempo real, generar señales de trading mediante inferencia causal y modelos predictivos, y clasificar el régimen de mercado por volatilidad.

### 5.2 Stack Técnico

**Archivo principal**: `python-ml/src/main.py`
**Dependencias clave** (de `requirements.txt`):

| Paquete | Versión | Uso |
|---------|---------|-----|
| `nats-py` | ≥2.6.0 | NATS client async |
| `dowhy` | ≥0.11 | Inferencia causal (backdoor criterion) |
| `econml` | ≥0.15 | Modelos econométricos |
| `scikit-learn` | ≥1.3.0 | ML utilities |
| `statsmodels` | ≥0.14.0 | Análisis estadístico |
| `pandas` | ≥2.1.0 | Data manipulation |
| `numpy` | ≥1.26.0 | Numerical computing |
| `httpx` | ≥0.26.0 | HTTP async client (QuestDB) |
| `structlog` | ≥24.1.0 | Structured logging |

### 5.3 Arquitectura del Pipeline

```
NATS: market.tick.>  ──▶  Price Buffer (per symbol)
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
             ┌───────────┐ ┌──────┐ ┌──────────┐
             │  Causal    │ │Pred. │ │ Regime   │
             │ Analyzer   │ │Model │ │Classifier│
             │  (DoWhy)   │ │(ARMA)│ │(K-Means) │
             └─────┬─────┘ └──┬───┘ └────┬─────┘
                   │           │          │
                   └───────────┼──────────┘
                               ▼
                      Signal Combiner
                               │
                   ┌───────────┼───────────┐
                   ▼           ▼           ▼
             NATS publish   QuestDB     Logging
             ml.signals.*  ml_signals
```

### 5.4 Componentes del ML Pipeline

#### 5.4.1 CausalAnalyzer (`src/models/causal_analyzer.py`)

- **Librería**: DoWhy (Microsoft Research)
- **Método**: Backdoor criterion para identificar relaciones causales
- **Lookback window**: 20 ticks (configurable via `CAUSAL_LOOKBACK`)
- **Output**: `causal_effect` (float) + `causal_description` (texto legible)
- **Fallback**: Si DoWhy falla → cálculo de correlación simple

#### 5.4.2 PredictiveModel (`src/models/predictive_model.py`)

- **Algoritmo**: ARIMA/Regression híbrido
- **Window**: 20 ticks
- **Output**: `predicted_close` + `confidence_low` + `confidence_high` (banda de confianza)
- **Retrain**: Cada 100 ticks nuevos (configurable via `MODEL_RETRAIN_INTERVAL`)

#### 5.4.3 RegimeClassifier (`src/models/regime_classifier.py`)

- **Algoritmo**: K-Means clustering sobre volatilidad anualizada
- **Regímenes**:
  - `LOW_VOL`: < 15% volatilidad anualizada
  - `MEDIUM_VOL`: 15-30%
  - `HIGH_VOL`: > 30%
- **Impacto**: Afecta umbrales de señal y sizing de posiciones

### 5.5 Generación de Señales

```python
expected_return = (predicted_close - current_price) / current_price
threshold = 0.004 if regime == "HIGH_VOL" else 0.002  # 0.4% o 0.2%

if expected_return > threshold:
    signal = "BUY"
elif expected_return < -threshold:
    signal = "SELL"
else:
    signal = "HOLD"
```

### 5.6 Tabla QuestDB: `ml_signals`

```sql
CREATE TABLE IF NOT EXISTS ml_signals (
  timestamp         TIMESTAMP,
  symbol            SYMBOL,
  exchange          SYMBOL,
  signal            STRING,     -- BUY, SELL, HOLD
  current_price     DOUBLE,
  predicted_close   DOUBLE,
  confidence_low    DOUBLE,
  confidence_high   DOUBLE,
  regime            STRING,     -- LOW_VOL, MEDIUM_VOL, HIGH_VOL
  causal_effect     DOUBLE,
  causal_description STRING,
  volatility        DOUBLE
) TIMESTAMP(timestamp) PARTITION BY DAY;
```

---

## 6. Servicio 3: Trading Agent — Ejecución Autónoma + Claude Decision Layer

### 6.1 Propósito

Servicio autónomo que recibe señales ML, las evalúa mediante un motor de decisión determinista + validación por Claude AI, y ejecuta trades en brokers reales con gestión de riesgo integral.

### 6.2 Stack Técnico

**Archivo principal**: `trading-agent/src/agent_loop.py`
**Dependencias clave**:

| Paquete | Versión | Uso |
|---------|---------|-----|
| `anthropic` | ≥0.39.0 | Claude API (Decision Layer) |
| `asyncpg` | ≥0.29.0 | PostgreSQL async |
| `httpx` | ≥0.26.0 | HTTP async (broker APIs, QuestDB) |
| `cryptography` | ≥42.0.0 | AES-256-GCM decrypt broker keys |
| `nats-py` | ≥2.6.0 | NATS client |
| `structlog` | ≥24.1.0 | Structured logging |

### 6.3 Arquitectura Multi-Usuario

```
┌──────────────────────────────────────────────────────┐
│                     AgentLoop                         │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  _configs     │  │  _clients    │  │  _tracker  │ │
│  │ dict[userId,  │  │ dict[userId, │  │  Position  │ │
│  │ AgentConfig]  │  │ BrokerClient]│  │  Tracker   │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  _risk_mgr   │  │   _scorer    │  │  _claude   │ │
│  │  RiskManager  │  │ ScoreTracker │  │ ClaudeLayer│ │
│  │ (per-user    │  │ (per-symbol  │  │ (circuit   │ │
│  │  daily P&L)  │  │  win rates)  │  │  breaker)  │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
└──────────────────────────────────────────────────────┘
```

- **Config Reload**: Cada 60s recarga configs de PostgreSQL (nuevos usuarios, cambios)
- **Position Sync**: Cada 30s sincroniza posiciones con broker (reconciliación)
- **State Isolation**: Cada usuario tiene su propia configuración, cliente de broker, y límites de riesgo

### 6.4 Pipeline de Decisión (por señal)

```
ML Signal (NATS)
     │
     ▼
[1] Normalize Symbol
     │
     ▼
[2] Per-User Filter (enabled? symbol allowed? broker connected?)
     │
     ▼
[3] Fetch Account Info (equity, buying power)
     │
     ▼
[4] Load Position Risks (stop loss, take profit)
     │
     ▼
[5] DecisionEngine.evaluate()  ──▶  OPEN_LONG | CLOSE | HOLD
     │                               (deterministic rules)
     ▼
[6] ClaudeLayer.evaluate()     ──▶  APPROVE | REJECT | REDUCE
     │                               (AI validation)
     ▼
[7] Apply Claude Recommendation
     │  REJECT → convert to HOLD
     │  REDUCE → multiply quantity by adjusted_size
     │  APPROVE → proceed as-is
     ▼
[8] Execute Trade via Broker API
     │
     ▼
[9] Save Order to PostgreSQL + Publish to NATS
     │
     ▼
[10] Update PositionTracker + ScoreTracker
```

### 6.5 Claude Decision Layer — Detalle Técnico

**Archivo**: `trading-agent/src/claude_layer.py`

#### Configuración del Modelo

| Parámetro | Valor |
|-----------|-------|
| Modelo | `claude-sonnet-4-20250514` |
| Max tokens | 600 |
| Temperature | 0.1 (baja, para consistencia) |
| Timeout | 12 segundos |
| Prompt caching | Habilitado (ephemeral cache en system prompt) |

#### System Prompt (Cacheado)

Claude actúa como **"quantitative trading analyst"** con reglas estrictas:

| Regla | Descripción |
|-------|-------------|
| Retorno mínimo | Nunca aprobar si expected return < 0.25% post-fees |
| Risk/Reward | Nunca aprobar si ratio < 1.5:1 |
| Win Rate | Nunca aprobar si win_rate < 45% (con > 5 trades históricos) |
| Banda de confianza | Reducir size si confidence band > 2% del precio |
| Alta volatilidad | Reducir size 50% en régimen HIGH_VOL |
| Drawdown | Rechazar si P&L diario negativo Y drawdown > 50% del máximo |

#### Contexto Enviado a Claude (User Prompt)

Cada evaluación incluye:
1. **Señal actual**: symbol, precio, predicción, banda de confianza, régimen, análisis causal
2. **Decisión del engine**: Recomendación del motor determinista
3. **Estado de cuenta**: equity, buying power, P&L diario, drawdown
4. **Posiciones abiertas**: con unrealized P&L
5. **Historial de señales**: últimas 10 para el symbol
6. **Score card**: win rate, avg win/loss, Sharpe ratio, P&L acumulado
7. **Reglas de riesgo**: stop loss, take profit calculados

#### Output Estructurado (JSON)

```json
{
  "execute": true,
  "confidence": 0.78,
  "adjusted_size_multiplier": 0.8,
  "reasoning": "Strong causal effect with favorable regime...",
  "expected_return_pct": 0.45,
  "expected_pnl_usd": 12.50,
  "risk_reward_ratio": 2.1,
  "fees_estimated_pct": 0.05,
  "recommendation": "APPROVE"
}
```

#### Circuit Breaker

- **Umbral**: 3 fallos consecutivos (timeout, error de API)
- **Cooldown**: 5 minutos
- **Comportamiento durante cooldown**: Trading Agent opera sin validación Claude (solo motor determinista)

#### Persistencia de Decisiones

| Destino | Tabla | Datos |
|---------|-------|-------|
| PostgreSQL | `ClaudeDecision` | Análisis completo + outcome tracking (WIN/LOSS) |
| QuestDB | `claude_decisions` | Serie temporal para analytics |

### 6.6 Gestión de Riesgo (RiskManager)

- **Daily Loss Limit**: Configurable por usuario (default varía por plan)
- **Max Drawdown**: Porcentaje máximo de pérdida desde equity máximo
- **Max Concurrent Positions**: Límite de posiciones abiertas simultáneas
- **Max Position Size (USD)**: Tope por posición individual
- **Stop Loss / Take Profit**: Calculados dinámicamente, almacenados en `PositionRisk`

### 6.7 Integración con Brokers

**Archivo base**: `trading-agent/src/brokers/base.py`
**Interface unificada**: `BrokerClient`

| Broker | Archivo | Mercado | Tipo | API |
|--------|---------|---------|------|-----|
| Alpaca | `brokers/alpaca.py` | US Stocks | Paper + Live | REST API v2 |
| Bitget | `brokers/bitget.py` | Crypto Spot | Live | REST API v2 |

**Operaciones soportadas**:
- `get_account()` → equity, buying power, currency
- `get_positions()` → symbol, quantity, avg price, unrealized P&L
- `place_order(symbol, side, quantity, order_type)` → order ID
- `cancel_order(order_id)` → success/failure
- `get_order(order_id)` → status, filled price, filled quantity

**Credenciales**: Almacenadas encriptadas en PostgreSQL, descifradas en runtime con AES-256-GCM.

### 6.8 Tabla QuestDB: `claude_decisions`

```sql
CREATE TABLE IF NOT EXISTS claude_decisions (
  timestamp        TIMESTAMP,
  user_id          SYMBOL,
  symbol           SYMBOL,
  action           STRING,
  recommendation   STRING,    -- APPROVE, REJECT, REDUCE
  confidence       DOUBLE,
  expected_return  DOUBLE,
  expected_pnl     DOUBLE,
  risk_reward_ratio DOUBLE,
  actual_pnl       DOUBLE,
  outcome          STRING,    -- WIN, LOSS, null (open)
  latency_ms       INT
) TIMESTAMP(timestamp) PARTITION BY DAY;
```

---

## 7. Servicio 4: Next.js Frontend — Aplicación Web SaaS

### 7.1 Propósito

Aplicación web SaaS que provee dashboard de trading en tiempo real, chat con Claude AI (Causal Copilot), gestión de broker/agent, analytics, billing con Stripe, y flujo de autenticación completo.

### 7.2 Stack Técnico

**Framework**: Next.js 14 (App Router)
**ORM**: Prisma 5.22+ con PostgreSQL 16
**Auth**: NextAuth 4.24+ (JWT strategy, 7 días maxAge)
**Styling**: Tailwind CSS con design tokens personalizados
**Charts**: Recharts 2.10+
**Animations**: Framer Motion 10.18+
**State**: React Query (TanStack Query 5.17+)
**Validation**: Zod 3.22+
**Notifications**: Sonner 2.0+

### 7.3 Design System — Tokens NexQuant

```css
--nq-bg:     #0a0e17   /* Fondo principal (casi negro azulado) */
--nq-card:   #111827   /* Tarjetas y paneles */
--nq-border: #1f2937   /* Bordes sutiles */
--nq-accent: #6366f1   /* Indigo (acción principal) */
--nq-green:  #10b981   /* Buy / Success */
--nq-red:    #ef4444   /* Sell / Error */
--nq-yellow: #f59e0b   /* Warning / Pending */
--nq-text:   #e5e7eb   /* Texto principal */
--nq-muted:  #6b7280   /* Texto secundario */
```

### 7.4 Estructura de Páginas

| Ruta | Archivo | Acceso | Descripción |
|------|---------|--------|-------------|
| `/` | `src/app/page.tsx` | Auth | Dashboard principal (redirect a onboarding si es nuevo) |
| `/analytics` | `src/app/analytics/page.tsx` | PRO | Dashboard de analytics con 5 charts |
| `/settings` | `src/app/settings/page.tsx` | Auth | Perfil, seguridad, brokers, agent, billing |
| `/onboarding` | `src/app/onboarding/page.tsx` | Auth | Wizard de 4 pasos para nuevos usuarios |
| `/auth/login` | `src/app/auth/login/page.tsx` | Public | Login con email/password + Google OAuth |
| `/auth/signup` | `src/app/auth/signup/page.tsx` | Public | Registro con email verification |
| `/auth/verify-email` | `src/app/auth/verify-email/page.tsx` | Public | Verificación de email + resend |
| `/auth/forgot-password` | `src/app/auth/forgot-password/page.tsx` | Public | Solicitud de reset de password |
| `/auth/reset-password` | `src/app/auth/reset-password/page.tsx` | Public | Formulario de nuevo password |
| `/terms` | `src/app/terms/page.tsx` | Public | Terms of Service |
| `/privacy` | `src/app/privacy/page.tsx` | Public | Privacy Policy |
| `/error` | `src/app/error.tsx` | — | Error boundary (App Router convention) |
| `/not-found` | `src/app/not-found.tsx` | — | Página 404 |

### 7.5 API Routes — Catálogo Completo (29 routes)

#### Autenticación (6 routes)

| Método | Ruta | Rate Limit | Descripción |
|--------|------|------------|-------------|
| * | `/api/auth/[...nextauth]` | — | NextAuth handler (login, logout, session) |
| POST | `/api/auth/signup` | 5/min/IP | Registro + envío de email de verificación |
| POST | `/api/auth/send-verification` | — | Re-enviar email de verificación (autenticado) |
| GET | `/api/auth/verify-email?token=X` | — | Validar token y marcar emailVerified=true |
| POST | `/api/auth/forgot-password` | 3/min/IP | Generar token reset (anti-enumeración: siempre 200) |
| POST | `/api/auth/reset-password` | — | Validar token + hashear nuevo password |

#### Broker Management (3 routes)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/broker` | Listar conexiones del usuario (sin credenciales) |
| POST | `/api/broker` | Conectar broker (encripta keys con AES-256-GCM) |
| DELETE | `/api/broker` | Desconectar broker |
| GET | `/api/broker/account` | Info de cuenta del broker activo |
| POST | `/api/broker/test` | Test de credenciales (errores sanitizados) |

#### Trading (5 routes)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/orders` | Historial de órdenes |
| POST | `/api/orders` | Colocar orden manual |
| POST | `/api/orders/sync` | Sincronizar estado de órdenes pendientes |
| POST | `/api/orders/[id]/cancel` | Cancelar orden |
| GET | `/api/positions` | Posiciones abiertas |
| POST | `/api/positions/close` | Cerrar posición |

#### Agent (2 routes)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/PUT | `/api/agent/config` | Configuración del agente autónomo |
| POST | `/api/agent/command` | Comandos: pause, resume, close_all |

#### Chat — Claude Causal Copilot (1 route)

| Método | Ruta | Rate Limit | Descripción |
|--------|------|------------|-------------|
| POST | `/api/chat` | 5/min/user | Chat con Claude Sonnet 4 + contexto de mercado |

**Detalle del Chat**:
- **Modelo**: `claude-sonnet-4-20250514`
- **Max tokens**: 500
- **System prompt**: "You are NexQuant Causal Copilot" con datos de mercado en tiempo real
- **Contexto inyectado**: Precios de QuestDB + señales ML + régimen de mercado
- **Plan guard**: FREE = 10 mensajes/día, PRO = ilimitado
- **Fallback**: Pattern matching local si Claude API no disponible

#### Analytics y Reports (4 routes)

| Método | Ruta | Plan | Descripción |
|--------|------|------|-------------|
| GET | `/api/analytics?range=30d` | PRO | Datos agregados para 5 charts |
| GET | `/api/portfolio` | Auth | Resumen de portfolio |
| GET | `/api/reports/trades?format=csv` | Auth | Exportación CSV de trades |
| GET | `/api/reports/performance` | Auth | Métricas mensuales de performance |

#### Señales (1 route)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/signals` | Señales ML más recientes de QuestDB |

#### Claude Decisions (1 route)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/claude-decisions` | Decisiones recientes de Claude con outcomes |

#### User Management (2 routes)

| Método | Ruta | Descripción |
|--------|------|-------------|
| PUT | `/api/user/profile` | Actualizar nombre/email (re-verificación si email cambia) |
| POST | `/api/user/change-password` | Cambiar password (verifica actual) |

#### Billing — Stripe (3 routes)

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/api/billing/create-checkout` | Auth | Crear sesión de Stripe Checkout |
| POST | `/api/billing/portal` | Auth | URL del portal de gestión de suscripción |
| POST | `/api/billing/webhook` | **Public** | Webhook de Stripe (verifica firma) |

**Eventos Stripe manejados**:
- `checkout.session.completed` → upgrade a PRO
- `customer.subscription.updated` → sincronizar estado
- `customer.subscription.deleted` → downgrade a FREE
- `invoice.payment_failed` → marcar como `past_due`

#### Audit (1 route)

| Método | Ruta | Plan | Descripción |
|--------|------|------|-------------|
| GET | `/api/audit-log?page=1` | PRO | Log de actividad paginado (20/página) |

### 7.6 Componentes Principales

| Componente | Archivo | Descripción |
|------------|---------|-------------|
| `Dashboard` | `src/components/Dashboard.tsx` | Contenedor principal, layout responsivo |
| `SwipeToInvest` | `src/components/SwipeToInvest.tsx` | Cards de señales con swipe (Framer Motion) |
| `ChatInterface` | `src/components/ChatInterface.tsx` | Chat con Claude Causal Copilot |
| `OrderConfirmation` | `src/components/OrderConfirmation.tsx` | Modal de confirmación de trade |
| `ClosePositionModal` | `src/components/ClosePositionModal.tsx` | Modal para cerrar posiciones |
| `PositionsView` | `src/components/PositionsView.tsx` | Tabla de posiciones abiertas |
| `PortfolioHealth` | `src/components/PortfolioHealth.tsx` | Métricas de portfolio en tiempo real |
| `AgentPanel` | `src/components/AgentPanel.tsx` | Panel de control del agente autónomo |
| `ClaudeInsights` | `src/components/ClaudeInsights.tsx` | Historial de decisiones Claude + win rate |
| `TradeHistory` | `src/components/TradeHistory.tsx` | Historial de órdenes con filtros y export CSV |
| `AnalyticsDashboard` | `src/components/AnalyticsDashboard.tsx` | 5 gráficos Recharts (P&L, win rate, etc.) |
| `Header` | `src/components/Header.tsx` | Navegación desktop + hamburger mobile |
| `MobileNav` | `src/components/MobileNav.tsx` | Bottom tab bar para mobile |
| `EmptyState` | `src/components/EmptyState.tsx` | Estado vacío reutilizable |

### 7.7 Middleware de Autenticación

**Archivo**: `src/middleware.ts`

```typescript
// Rutas públicas (no requieren JWT)
const PUBLIC_PATHS = [
  '/auth/',
  '/api/auth/',
  '/api/billing/webhook',
  '/terms',
  '/privacy'
];
```

- Verifica JWT token en cada request
- Redirect a `/auth/login` si no autenticado
- Excluye: `_next`, `favicon.ico`, archivos estáticos, rutas públicas

### 7.8 Plan Guard — Sistema de Planes

**Archivo**: `src/lib/plan-guard.ts`

| Feature | FREE | PRO |
|---------|------|-----|
| Chat mensajes/día | 10 | Ilimitado |
| Exchanges | CRYPTO solamente | US, CRYPTO, LSE, BME, TSE |
| Trading autónomo | No | Sí |
| Analytics dashboard | No | Sí |
| Export CSV | Sí | Sí |
| Audit log | No | Sí |

### 7.9 Rate Limiting

**Archivo**: `src/lib/rate-limit.ts`

| Instancia | Límite | Aplicado en |
|-----------|--------|-------------|
| `signupLimiter` | 5/min/IP | POST `/api/auth/signup` |
| `loginLimiter` | 10/min/IP | POST `/api/auth/callback/credentials` |
| `chatLimiter` | 5/min/user | POST `/api/chat` |
| `forgotPasswordLimiter` | 3/min/IP | POST `/api/auth/forgot-password` |

**Implementación**: Sliding window in-memory (sin Redis). `Map<key, timestamp[]>` con cleanup periódico cada 60s.

---

## 8. Flujo End-to-End: Del Dato de Mercado a la Ejecución del Trade

### 8.1 Fase 1: Ingesta de Datos (Rust Engine)

```
T+0ms: WebSocket recibe tick de Alpaca (ej: AAPL $178.52)
T+1ms: Parse JSON → MarketTick struct
T+2ms: Broadcast via tokio::broadcast::channel
T+3ms: NATS publish → "market.tick.US.AAPL"
T+5ms: HTTP POST → QuestDB (batch, cada 10 ticks)
```

### 8.2 Fase 2: Análisis ML (Python ML)

```
T+10ms: NATS subscriber recibe tick
T+11ms: Agrega al buffer de AAPL (window=20)
T+5000ms: (cada 5s) Trigger análisis:
  T+5001ms: CausalAnalyzer.analyze() → causal_effect=0.12
  T+5050ms: PredictiveModel.predict() → predicted=$179.15, CI=[178.80, 179.50]
  T+5060ms: RegimeClassifier.classify() → MEDIUM_VOL
  T+5070ms: Signal combiner → BUY (expected return 0.35%)
  T+5075ms: NATS publish → "ml.signals.composite"
  T+5080ms: HTTP POST → QuestDB ml_signals
```

### 8.3 Fase 3: Decisión + Ejecución (Trading Agent)

```
T+5085ms: NATS subscriber recibe señal BUY AAPL
T+5090ms: Para cada usuario con agente activo:
  T+5091ms: Verificar: ¿AAPL en allowed_symbols? ¿Broker conectado? ¿Agent enabled?
  T+5095ms: Fetch account info de Alpaca → equity=$10,000, buying_power=$5,000
  T+5100ms: DecisionEngine.evaluate():
    - Max position size: $500 (5% of equity)
    - Quantity: floor($500 / $178.52) = 2 shares
    - Stop loss: $178.52 * 0.97 = $173.16
    - Take profit: $178.52 * 1.03 = $183.88
    → Decisión: OPEN_LONG, qty=2
  T+5110ms: ClaudeLayer.evaluate():
    - Envía context completo a Claude Sonnet 4
    - Claude analiza: expected return 0.35%, risk/reward 1.8:1, win_rate 52%
    → Response: APPROVE, confidence=0.72, adjusted_size=1.0
  T+5500ms: (latencia Claude ~400ms)
  T+5510ms: Alpaca API: POST /v2/orders → order_id="abc123"
  T+5600ms: Save Order to PostgreSQL (status=PENDING)
  T+5610ms: Save ClaudeDecision to PostgreSQL + QuestDB
  T+5620ms: NATS publish → "agent.decisions.{userId}"
```

### 8.4 Fase 4: Visualización (Next.js Frontend)

```
T+5625ms: Browser recibe decisión via NATS WebSocket
T+5630ms: React Query invalida cache de 'positions' y 'trade-history'
T+5635ms: UI actualiza:
  - TradeHistory: nueva orden PENDING
  - PositionsView: nueva posición AAPL
  - ClaudeInsights: nueva decisión con reasoning
  - PortfolioHealth: equity actualizado
```

### 8.5 Fase 5: Tracking de Outcome

```
T+N (cuando se cierra la posición):
  - Trading Agent detecta cierre (manual o stop/take profit)
  - Calcula actual_pnl
  - Actualiza ClaudeDecision: outcome=WIN/LOSS, actualPnl=+$3.50
  - ScoreTracker actualiza win_rate, Sharpe ratio
  - QuestDB: UPDATE claude_decisions SET actual_pnl, outcome
```

### Latencia Total Estimada

| Fase | Latencia |
|------|----------|
| Data ingestion (WebSocket → NATS) | ~5ms |
| ML analysis (cuando se ejecuta, cada 5s) | ~80ms |
| Claude evaluation | ~400ms |
| Broker API execution | ~100-200ms |
| **Total (signal → order)** | **~500-700ms** |

---

## 9. Sistemas Externos e Integraciones

### 9.1 Proveedores de Datos de Mercado

| Proveedor | Uso | Protocolo | Archivo |
|-----------|-----|-----------|---------|
| **Alpaca Markets** | Datos IEX free-tier (US stocks) | WebSocket | `rust-engine/src/market_data/alpaca_source.rs` |
| **Finnhub** | Datos de LSE, BME, TSE | WebSocket | `rust-engine/src/market_data/finnhub_source.rs` |
| **Bitget** | Datos crypto spot 24/7 | WebSocket | `rust-engine/src/market_data/bitget_source.rs` |

### 9.2 Brokers de Ejecución

| Broker | Uso | API | Archivos |
|--------|-----|-----|----------|
| **Alpaca** | Paper + Live trading (US) | REST v2 | `trading-agent/src/brokers/alpaca.py`, `nextjs-frontend/src/app/api/orders/route.ts` |
| **Bitget** | Spot trading (Crypto) | REST v2 | `trading-agent/src/brokers/bitget.py`, `nextjs-frontend/src/app/api/orders/route.ts` |

### 9.3 Servicios de AI

| Servicio | Uso | Modelo | Archivos |
|----------|-----|--------|----------|
| **Anthropic (Claude)** | Decision Layer (Trading Agent) | `claude-sonnet-4-20250514` | `trading-agent/src/claude_layer.py` |
| **Anthropic (Claude)** | Causal Copilot Chat (Frontend) | `claude-sonnet-4-20250514` | `nextjs-frontend/src/app/api/chat/route.ts` |

### 9.4 Servicios de Infraestructura

| Servicio | Uso | Archivos |
|----------|-----|----------|
| **NATS** (self-hosted) | Message bus entre servicios | `infrastructure/nats/nats.conf`, `docker-compose.yml` |
| **QuestDB** (self-hosted) | Base de datos time-series | `infrastructure/questdb/server.conf`, `docker-compose.yml` |
| **PostgreSQL 16** (self-hosted) | Base de datos relacional | `docker-compose.yml`, `prisma/schema.prisma` |

### 9.5 Servicios SaaS de Terceros

| Servicio | Uso | Archivos |
|----------|-----|----------|
| **Stripe** | Billing, suscripciones, checkout | `nextjs-frontend/src/lib/stripe.ts`, `src/app/api/billing/*` |
| **Resend** | Emails transaccionales (verificación, reset) | `nextjs-frontend/src/lib/email.ts` |
| **Google OAuth** | Login social (opcional) | `nextjs-frontend/src/lib/auth.ts` |

### 9.6 Variables de Entorno Requeridas

#### Credenciales de Proveedores de Datos

```env
ALPACA_API_KEY=           # Alpaca paper/live API key
ALPACA_API_SECRET=        # Alpaca API secret
ALPACA_WS_URL=            # wss://stream.data.alpaca.markets/v2/iex
FINNHUB_API_KEY=          # Finnhub free/premium key
FINNHUB_WS_URL=           # wss://ws.finnhub.io
# Bitget: no requiere API key para datos públicos
```

#### Credenciales de Servicios

```env
ANTHROPIC_API_KEY=        # Claude API key (required para chat + trading)
STRIPE_SECRET_KEY=        # Stripe secret key
STRIPE_PUBLISHABLE_KEY=   # Stripe publishable key (client-side)
STRIPE_WEBHOOK_SECRET=    # Stripe webhook signing secret
STRIPE_PRO_PRICE_ID=      # Price ID del plan PRO
RESEND_API_KEY=           # Resend API key para emails
FROM_EMAIL=               # "NexQuant <noreply@nexquant.app>"
GOOGLE_CLIENT_ID=         # Google OAuth client ID (opcional)
GOOGLE_CLIENT_SECRET=     # Google OAuth secret (opcional)
```

#### Seguridad

```env
ENCRYPTION_KEY=           # 64-char hex (32 bytes) para AES-256-GCM
NEXTAUTH_SECRET=          # JWT signing secret
NEXTAUTH_URL=             # http://localhost:3005 (o dominio de producción)
```

#### Conexiones Internas

```env
NATS_URL=nats://nats:4222
QUESTDB_URL=http://questdb:9000
DATABASE_URL=postgresql://nexquant:password@postgres:5432/nexquant
POSTGRES_PASSWORD=        # Password de PostgreSQL
```

---

## 10. Seguridad

### 10.1 Autenticación

| Mecanismo | Detalle |
|-----------|---------|
| **JWT Strategy** | NextAuth con JWT, maxAge 7 días |
| **Password Hashing** | bcryptjs (salt rounds: 10) |
| **Email Verification** | UUID token, 24h expiración |
| **Password Reset** | UUID token, 1h expiración, anti-enumeración |
| **OAuth** | Google OAuth 2.0 (opcional) |

### 10.2 Encriptación

| Dato | Algoritmo | Archivo |
|------|-----------|---------|
| Broker API keys | AES-256-GCM | `src/lib/encryption.ts` |
| Broker API secrets | AES-256-GCM | `src/lib/encryption.ts` |
| Broker extra params | AES-256-GCM | `src/lib/encryption.ts` |

**Formato de almacenamiento**: `iv:authTag:ciphertext` (hex-encoded)
**Key**: 64 caracteres hex (32 bytes) desde `ENCRYPTION_KEY`

### 10.3 Protección contra Inyección

| Tipo | Protección | Archivo |
|------|-----------|---------|
| SQL Injection (QuestDB) | `sanitizeSymbol()` regex whitelist `[a-zA-Z0-9.:_-]` | `src/lib/questdb-client.ts` |
| SQL Injection (QuestDB) | `sanitizeLimit()` valida entero positivo finito | `src/lib/questdb-client.ts` |
| SQL Injection (PostgreSQL) | Prisma ORM (parameterized queries) | Todos los API routes |

### 10.4 Rate Limiting

| Endpoint | Límite | Tipo |
|----------|--------|------|
| Signup | 5/min | Por IP |
| Login | 10/min | Por IP |
| Chat | 5/min | Por usuario |
| Forgot Password | 3/min | Por IP |

**Implementación**: Sliding window in-memory con cleanup automático cada 60s.

### 10.5 Sanitización de Errores

- Errores de broker: mensajes genéricos al cliente, logs detallados server-side
- Errores de base de datos: nunca expuestos al cliente
- Stack traces: solo en `NODE_ENV=development`

### 10.6 Middleware de Autorización

- JWT token verificado en cada request (excepto PUBLIC_PATHS)
- Plan-based access control (FREE vs PRO) en endpoints específicos
- User-scoped queries: todos los datos filtrados por `userId` de la sesión

---

## 11. Esquema de Base de Datos

### 11.1 PostgreSQL (Prisma) — 7 Modelos

```
┌───────────┐     ┌──────────────────┐     ┌────────────┐
│   User    │────▶│ BrokerConnection │     │  Account   │
│           │     │ (encrypted keys) │     │  (OAuth)   │
│           │────▶│                  │     │            │
│           │     └──────────────────┘     └────────────┘
│           │
│           │────▶┌──────────────────┐
│           │     │     Order        │
│           │     │ (trade history)  │
│           │     └──────────────────┘
│           │
│           │────▶┌──────────────────┐
│           │     │  PositionRisk    │
│           │     │ (SL/TP rules)    │
│           │     └──────────────────┘
│           │
│           │────▶┌──────────────────┐
│           │     │  AgentConfig     │
│           │     │ (1:1 per user)   │
│           │     └──────────────────┘
│           │
│           │────▶┌──────────────────┐
│           │     │ ClaudeDecision   │
│           │     │ (AI decisions)   │
│           │     └──────────────────┘
│           │
│           │────▶┌──────────────────┐
│           │     │   AuditLog       │
│           │     │ (activity log)   │
└───────────┘     └──────────────────┘
```

#### Modelo User (campos clave)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | String (CUID) | Primary key |
| email | String (unique) | Email de login |
| hashedPassword | String? | bcrypt hash (null para OAuth users) |
| name | String? | Nombre display |
| plan | Enum (FREE/PRO) | Plan actual |
| emailVerified | Boolean | ¿Email verificado? |
| verificationToken | String? | Token de verificación pendiente |
| verificationExpiry | DateTime? | Expiración del token (24h) |
| resetToken | String? | Token de reset de password |
| resetExpiry | DateTime? | Expiración del reset (1h) |
| onboardingCompleted | Boolean | ¿Completó onboarding? |
| stripeCustomerId | String? (unique) | Stripe customer ID |
| subscriptionId | String? | Stripe subscription ID |
| subscriptionStatus | String? | active, past_due, cancelled |
| chatUsageToday | Int | Contador de chats hoy (FREE plan) |
| chatResetDate | DateTime? | Fecha de reset del contador |

#### Modelo BrokerConnection

| Campo | Tipo | Descripción |
|-------|------|-------------|
| broker | Enum (ALPACA/BITGET) | Tipo de broker |
| encryptedKey | String | API key encriptada (AES-256-GCM) |
| encryptedSecret | String | API secret encriptada |
| encryptedExtra | String? | Passphrase u otros (ej: Bitget) |
| label | String? | Etiqueta del usuario |
| isActive | Boolean | ¿Es la conexión activa? |
| **Unique**: userId + broker | | Un broker por usuario |

#### Modelo ClaudeDecision

| Campo | Tipo | Descripción |
|-------|------|-------------|
| symbol | String | Symbol evaluado |
| action | String | OPEN_LONG, CLOSE, HOLD |
| mlSignal | Json | Señal ML completa |
| claudeAnalysis | Json | Respuesta completa de Claude |
| recommendation | String | APPROVE, REJECT, REDUCE |
| confidence | Float | 0.0-1.0 |
| expectedReturn | Float? | Expected return % |
| expectedPnl | Float? | Expected P&L USD |
| riskRewardRatio | Float? | Risk/Reward ratio |
| adjustedSize | Float? | Size multiplier (0.0-1.0) |
| entryPrice | Float? | Precio de entrada |
| exitPrice | Float? | Precio de salida |
| actualPnl | Float? | P&L real |
| outcome | String? | WIN, LOSS |
| executionStatus | String | EXECUTED, SKIPPED, FAILED, TIMEOUT |
| latencyMs | Int? | Latencia de Claude en ms |

### 11.2 QuestDB — 3 Tablas Time-Series

| Tabla | Partición | Creada por | Registros/día estimados |
|-------|-----------|------------|------------------------|
| `market_data` | DAY | Rust Engine | ~2.16M (25 symbols × 1Hz × 86,400s) |
| `ml_signals` | DAY | Python ML | ~432K (25 symbols × 12/min × 1,440min) |
| `claude_decisions` | DAY | Trading Agent | ~500-2000 (depende de actividad) |

---

## 12. Evaluación: Puntos Positivos

### 12.1 Arquitectura

1. **Microservicios bien separados**: Cada servicio tiene una responsabilidad clara (ingesta, ML, decisión, UI). Los servicios se comunican exclusivamente via NATS, lo que permite escalar, reemplazar o modificar cada uno independientemente.

2. **Elección acertada de tecnologías por capa**:
   - Rust para ingesta de datos: máximo throughput, mínima latencia, zero-cost abstractions
   - Python para ML: ecosistema completo (DoWhy, scikit-learn, pandas)
   - TypeScript/Next.js para frontend: developer experience, SSR, App Router

3. **NATS como message bus**: Excelente elección para este caso de uso. JetStream proporciona persistencia sin la complejidad de Kafka, y el soporte WebSocket nativo permite que el browser consuma datos en tiempo real.

4. **QuestDB para time-series**: Rendimiento superior a PostgreSQL para queries temporales, con particionado automático por día y tipo SYMBOL indexado.

5. **HybridSource pattern**: Solución elegante para el problema de mercados cerrados. El auto-fallback a MockSource permite desarrollo y testing 24/7 sin depender de mercados abiertos.

### 12.2 Seguridad

6. **Claude Decision Layer**: Innovador y bien implementado. La combinación de motor determinista + validación AI proporciona una capa de seguridad superior contra trades irracionales. Las reglas hardcoded en el prompt (min return, risk/reward, win rate) actúan como guardrails objetivos.

7. **Circuit breaker en Claude**: Previene cascading failures si la API de Anthropic tiene problemas. El agente continúa operando con el motor determinista.

8. **AES-256-GCM para credenciales de broker**: Estándar de industria. El formato iv:authTag:ciphertext es correcto y la clave de 32 bytes es suficiente.

9. **SQL injection prevention en QuestDB**: La función `sanitizeSymbol()` con regex whitelist es la protección correcta para queries que no pueden usar parameterized queries.

10. **Anti-enumeración en forgot-password**: Siempre retorna 200 independientemente de si el email existe, previniendo enumeración de usuarios.

### 12.3 Producto

11. **UX de SwipeToInvest**: Interfaz innovadora tipo Tinder para señales de trading. Reduce la fricción de decisión para el usuario.

12. **Prompt caching en Claude**: Reduce costos de API ~90% al cachear el system prompt (que es largo y estático) como ephemeral.

13. **Outcome tracking**: El sistema no solo genera señales y ejecuta trades, sino que cierra el loop rastreando WIN/LOSS por decisión, permitiendo evaluar la efectividad del sistema.

14. **Multi-market desde día 1**: Soporte para 5 exchanges y 25 symbols, con arquitectura extensible.

15. **Modelo de negocio claro**: FREE tier para atraer usuarios (crypto only, 10 chats/día) → PRO tier para monetizar (all markets, trading, analytics).

### 12.4 Código y Prácticas

16. **Lazy initialization pattern**: Para Stripe y Resend, evitando fallos en build-time cuando las API keys no están disponibles.

17. **Structured logging**: `structlog` en Python y `tracing` en Rust proporcionan logs consistentes y parseables.

18. **Audit logging**: Registro de actividad para compliance y debugging (login, broker connect, order place, etc.).

19. **Responsive design**: Mobile-first con MobileNav bottom bar, hamburger menu, y reordenamiento de layout.

20. **Error boundaries y 404**: Manejo robusto de errores a nivel de aplicación con UI styled.

---

## 13. Evaluación: Puntos Críticos y Débiles

### 13.1 Críticos — Deben resolverse antes del lanzamiento

#### C1: Rate Limiter In-Memory No Escala

**Severidad**: 🔴 Crítica
**Archivo**: `src/lib/rate-limit.ts`

El rate limiter usa un `Map` en memoria del proceso Node.js. En producción con múltiples instancias o restarts, el estado se pierde. Un atacante solo necesita esperar un restart del contenedor para resetear todos los contadores.

**Recomendación**: Migrar a Redis/Valkey para rate limiting distribuido, o al menos usar `Upstash Redis` (serverless) para mantener la simplicidad.

#### C2: NATS WebSocket Sin TLS

**Severidad**: 🔴 Crítica
**Archivo**: `infrastructure/nats/nats.conf` → `no_tls: true`

Los datos de mercado y señales de trading viajan sin encriptar entre el browser y NATS. En producción, esto expone datos sensibles a MITM attacks.

**Recomendación**: Configurar TLS con certificados (Let's Encrypt) para el WebSocket de NATS. Esto es obligatorio para producción.

#### C3: Sin Tests

**Severidad**: 🔴 Crítica

No existe una suite de tests (unit, integration, e2e) en ninguno de los 4 servicios. Esto hace imposible validar que cambios futuros no rompan funcionalidad existente.

**Recomendación**:
- Rust: `cargo test` con mocks de NATS/QuestDB
- Python: `pytest` con fixtures para ML pipeline
- Next.js: `jest` para API routes + `Playwright` para e2e
- Priorizar tests para: Claude Decision Layer, order execution, encryption/decryption

#### C4: Secret Management

**Severidad**: 🔴 Crítica

Las API keys (Anthropic, Stripe, Alpaca, Finnhub, Resend) se pasan como variables de entorno en `docker-compose.yml`. En producción, estas deben venir de un secret manager (AWS Secrets Manager, HashiCorp Vault, o similar).

**Recomendación**: Implementar secret rotation y un vault para producción. Como mínimo, usar Docker Secrets.

#### C5: Sin HTTPS para el Frontend

**Severidad**: 🔴 Crítica

El frontend corre en HTTP (`http://localhost:3005`). NextAuth requiere HTTPS en producción para cookies seguras.

**Recomendación**: Agregar un reverse proxy (Nginx/Caddy) con TLS termination delante del frontend.

### 13.2 Importantes — Deben resolverse a corto plazo

#### I1: Python ML Sin Healthcheck

**Severidad**: 🟡 Importante
**Archivo**: `docker-compose.yml`

El servicio `python-ml` no tiene healthcheck en Docker Compose. Si el proceso crashea silenciosamente, no se detecta. Los otros servicios (trading-agent) dependen de sus señales.

**Recomendación**: Agregar un healthcheck HTTP (similar a rust-engine y trading-agent).

#### I2: QuestDB Healthcheck Frágil

**Severidad**: 🟡 Importante
**Archivo**: `docker-compose.yml`

El healthcheck de QuestDB usa `bash -c 'echo > /dev/tcp/localhost/9000'` (TCP socket test). Esto verifica que el puerto está abierto, pero no que QuestDB está procesando queries correctamente.

**Recomendación**: Usar HTTP health endpoint: `curl -s http://localhost:9000/exec?query=SELECT+1` (nota: QuestDB 7.3.10 no incluye curl, considerar usar la imagen con herramientas o un sidecar).

#### I3: Sin Monitoreo / Alerting

**Severidad**: 🟡 Importante

No hay sistema de monitoreo (Prometheus, Grafana, Datadog) ni alertas. En producción, problemas como: circuit breaker activado, broker API timeouts, o ML pipeline stalled no se detectarían hasta que el usuario reporte.

**Recomendación**: Agregar Prometheus exporters para cada servicio, Grafana dashboards, y alertas básicas (PagerDuty/Slack).

#### I4: Sin Backups Automatizados

**Severidad**: 🟡 Importante

Los volúmenes de PostgreSQL y QuestDB no tienen backup automatizado. La pérdida de datos sería catastrófica.

**Recomendación**: Implementar `pg_dump` programado para PostgreSQL y snapshots de QuestDB. Almacenar en S3 o similar.

#### I5: Claude Fallback en Chat Muy Básico

**Severidad**: 🟡 Importante
**Archivo**: `src/app/api/chat/route.ts`

Cuando Claude API no está disponible, el chat cae a pattern matching local que solo detecta keywords. La experiencia de usuario degrada significativamente.

**Recomendación**: Implementar un fallback más robusto (modelo local pequeño, o al menos mensajes informativos que dirijan al usuario a las señales ML directamente).

#### I6: Sin Logging Centralizado

**Severidad**: 🟡 Importante

Cada servicio loggea a stdout/stderr de su contenedor. No hay agregación centralizada (ELK, Loki, CloudWatch).

**Recomendación**: Agregar un driver de logging de Docker que envíe a un servicio centralizado.

### 13.3 Mejorables — Mejoras de calidad

#### M1: Polling en vez de Push para Frontend

**Severidad**: 🟢 Mejora
**Archivos**: Múltiples componentes con `refetchInterval`

El frontend usa polling (React Query `refetchInterval`) para actualizar datos:
- TradeHistory: 15s
- Positions: periódico
- Claude Insights: periódico

Aunque NATS WebSocket está disponible (puerto 8223), los componentes no lo usan directamente.

**Recomendación**: Implementar un hook `useNATSSubscription()` que se suscriba a subjects NATS desde el browser para updates instantáneos.

#### M2: Sin Idempotencia en Orders API

**Severidad**: 🟢 Mejora
**Archivo**: `src/app/api/orders/route.ts`

Si una request de orden falla a nivel de red pero el broker sí ejecutó, un retry creará una orden duplicada.

**Recomendación**: Implementar idempotency key pattern (UUID generado por el cliente, verificado server-side).

#### M3: Sin Pagination en Trade History

**Severidad**: 🟢 Mejora
**Archivo**: `src/components/TradeHistory.tsx`

El componente carga todas las órdenes y las filtra client-side. Con muchas órdenes, esto se volverá lento.

**Recomendación**: Implementar pagination server-side con cursor-based pagination en el API.

#### M4: Onboarding No Persiste Datos

**Severidad**: 🟢 Mejora
**Archivo**: `src/app/onboarding/page.tsx`

El wizard de onboarding presenta 4 pasos pero la conexión de broker y configuración de agente en el paso 2 y 3 no están realmente integrados con los APIs existentes.

**Recomendación**: Conectar los formularios del onboarding con `/api/broker` y `/api/agent/config`.

#### M5: Single Point of Failure en NATS

**Severidad**: 🟢 Mejora

NATS corre como instancia única. Si se cae, toda la comunicación inter-servicio se detiene.

**Recomendación**: Para producción, implementar NATS cluster (3 nodos mínimo) o NATS Leaf Nodes.

#### M6: Sin CI/CD Pipeline

**Severidad**: 🟢 Mejora

No existe configuración de CI/CD (GitHub Actions, GitLab CI, etc.). Los deploys son manuales.

**Recomendación**: Implementar pipeline con: lint → test → build → push images → deploy (al menos staging).

#### M7: Performance del Build de Next.js en Docker

**Severidad**: 🟢 Mejora

El build de Next.js en Docker incluye `--no-cache` frecuentemente para evitar problemas. El Dockerfile podría optimizarse mejor con layer caching.

**Recomendación**: Revisar Dockerfile para asegurar que `npm ci` y `next build` tengan layers correctamente separadas.

---

## 14. Recomendaciones de Mejora para Lanzamiento

### 14.1 Prioridad Inmediata (Pre-Launch)

| # | Acción | Esfuerzo | Impacto |
|---|--------|----------|---------|
| 1 | Agregar HTTPS (Nginx/Caddy reverse proxy) | 2-4h | Seguridad |
| 2 | TLS para NATS WebSocket | 2-3h | Seguridad |
| 3 | Migrar rate limiter a Redis/Upstash | 4-6h | Seguridad |
| 4 | Secret management (al menos Docker Secrets) | 3-4h | Seguridad |
| 5 | Tests críticos (Claude Layer, Orders, Encryption) | 2-3 días | Estabilidad |
| 6 | Healthcheck para Python ML | 1h | Estabilidad |
| 7 | Backup automatizado (pg_dump cron) | 2-3h | Datos |

### 14.2 Prioridad Alta (Primeras Semanas Post-Launch)

| # | Acción | Esfuerzo | Impacto |
|---|--------|----------|---------|
| 8 | Monitoreo (Prometheus + Grafana) | 1-2 días | Operaciones |
| 9 | Logging centralizado (Loki/ELK) | 1 día | Debugging |
| 10 | CI/CD pipeline (GitHub Actions) | 1 día | Desarrollo |
| 11 | NATS WebSocket en componentes (reemplazar polling) | 2-3 días | UX |
| 12 | Idempotencia en Orders API | 4-6h | Fiabilidad |
| 13 | Pagination server-side en TradeHistory | 4h | Performance |

### 14.3 Prioridad Media (Mes 1-2)

| # | Acción | Esfuerzo | Impacto |
|---|--------|----------|---------|
| 14 | NATS cluster (3 nodos) | 1 día | Alta disponibilidad |
| 15 | Test e2e con Playwright | 2-3 días | Calidad |
| 16 | Integrar onboarding con APIs reales | 1 día | Onboarding |
| 17 | Fallback de chat mejorado | 1 día | UX |
| 18 | Performance profiling (Lighthouse, bundle analysis) | 1 día | Performance |

---

## 15. Apéndices

### A. Estructura de Directorios del Proyecto

```
NextQuant/
├── docker-compose.yml
├── .env                        # Variables de entorno (no versionado)
├── infrastructure/
│   ├── nats/
│   │   └── nats.conf           # Configuración NATS JetStream
│   └── questdb/
│       └── server.conf         # Configuración QuestDB
├── rust-engine/
│   ├── Dockerfile
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs
│       ├── config.rs
│       ├── market_data/
│       │   ├── source.rs       # DataSource trait
│       │   ├── alpaca_source.rs
│       │   ├── finnhub_source.rs
│       │   ├── bitget_source.rs
│       │   ├── mock_source.rs
│       │   ├── hybrid_source.rs
│       │   └── market_hours.rs
│       ├── events/
│       │   └── publisher.rs    # NATS publisher
│       └── storage/
│           └── questdb.rs      # QuestDB HTTP client
├── python-ml/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── main.py             # MLService + NATS loop
│       └── models/
│           ├── causal_analyzer.py
│           ├── predictive_model.py
│           └── regime_classifier.py
├── trading-agent/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── agent_loop.py       # Main agent loop
│       ├── claude_layer.py     # Claude Decision Layer
│       ├── decision_engine.py  # Deterministic rules
│       ├── risk_manager.py     # Risk management
│       ├── score_tracker.py    # Win rate / Sharpe tracking
│       ├── position_tracker.py # Position reconciliation
│       └── brokers/
│           ├── base.py         # BrokerClient interface
│           ├── alpaca.py       # Alpaca implementation
│           └── bitget.py       # Bitget implementation
└── nextjs-frontend/
    ├── Dockerfile
    ├── package.json
    ├── next.config.js
    ├── tailwind.config.ts
    ├── prisma/
    │   └── schema.prisma       # 7 modelos + 2 enums
    └── src/
        ├── middleware.ts       # Auth middleware
        ├── app/
        │   ├── layout.tsx
        │   ├── page.tsx        # Dashboard
        │   ├── error.tsx       # Error boundary
        │   ├── not-found.tsx   # 404
        │   ├── providers.tsx   # React Query + Sonner
        │   ├── analytics/page.tsx
        │   ├── settings/page.tsx
        │   ├── onboarding/page.tsx
        │   ├── terms/page.tsx
        │   ├── privacy/page.tsx
        │   ├── auth/
        │   │   ├── login/page.tsx
        │   │   ├── signup/page.tsx
        │   │   ├── verify-email/page.tsx
        │   │   ├── forgot-password/page.tsx
        │   │   └── reset-password/page.tsx
        │   └── api/
        │       ├── auth/[...nextauth]/route.ts
        │       ├── auth/signup/route.ts
        │       ├── auth/send-verification/route.ts
        │       ├── auth/verify-email/route.ts
        │       ├── auth/forgot-password/route.ts
        │       ├── auth/reset-password/route.ts
        │       ├── broker/route.ts
        │       ├── broker/account/route.ts
        │       ├── broker/test/route.ts
        │       ├── orders/route.ts
        │       ├── orders/sync/route.ts
        │       ├── orders/[id]/cancel/route.ts
        │       ├── positions/route.ts
        │       ├── positions/close/route.ts
        │       ├── agent/config/route.ts
        │       ├── agent/command/route.ts
        │       ├── chat/route.ts
        │       ├── claude-decisions/route.ts
        │       ├── signals/route.ts
        │       ├── portfolio/route.ts
        │       ├── analytics/route.ts
        │       ├── reports/trades/route.ts
        │       ├── reports/performance/route.ts
        │       ├── user/profile/route.ts
        │       ├── user/change-password/route.ts
        │       ├── billing/create-checkout/route.ts
        │       ├── billing/portal/route.ts
        │       ├── billing/webhook/route.ts
        │       └── audit-log/route.ts
        ├── components/
        │   ├── Dashboard.tsx
        │   ├── Header.tsx
        │   ├── MobileNav.tsx
        │   ├── SwipeToInvest.tsx
        │   ├── ChatInterface.tsx
        │   ├── OrderConfirmation.tsx
        │   ├── ClosePositionModal.tsx
        │   ├── PositionsView.tsx
        │   ├── PortfolioHealth.tsx
        │   ├── AgentPanel.tsx
        │   ├── ClaudeInsights.tsx
        │   ├── TradeHistory.tsx
        │   ├── AnalyticsDashboard.tsx
        │   └── EmptyState.tsx
        └── lib/
            ├── auth.ts          # NextAuth config
            ├── prisma.ts        # Prisma singleton
            ├── encryption.ts    # AES-256-GCM
            ├── questdb-client.ts # QuestDB queries
            ├── plan-guard.ts    # FREE/PRO limits
            ├── rate-limit.ts    # In-memory rate limiter
            ├── email.ts         # Resend integration
            ├── stripe.ts        # Stripe lazy init
            └── audit.ts         # Audit logger
```

### B. Symbols Soportados por Exchange

| Exchange | Provider | Symbols |
|----------|----------|---------|
| **CRYPTO** | Bitget | BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, ADAUSDT |
| **US** | Alpaca IEX | AAPL, GOOGL, MSFT, AMZN, TSLA |
| **LSE** | Finnhub | VOD.L, BP.L, HSBA.L, AZN.L, SHEL.L |
| **BME** | Finnhub | SAN.MC, TEF.MC, IBE.MC, ITX.MC, BBVA.MC |
| **TSE** | Finnhub | 7203.T, 6758.T, 9984.T, 8306.T, 6861.T |

### C. Decisiones Arquitectónicas Clave

| Decisión | Alternativa Rechazada | Razón |
|----------|----------------------|-------|
| Rust custom engine | barter-rs | Bugs críticos (race conditions, phantom orders), disclaimer legal contra producción |
| NATS (microservices) | PyO3 (FFI Rust↔Python) | GIL causa spikes de 10-80ms en hot path |
| QuestDB | TimescaleDB | Mejor rendimiento write para time-series, menor overhead |
| Claude Sonnet 4 | GPT-4, Claude Opus | Balance óptimo costo/latencia/calidad para decisiones de trading |
| Prompt caching | No caching | ~90% reducción de costos de API Claude |
| In-memory rate limiter | Redis | Simplicidad inicial (debe migrar a Redis para producción) |
| Docker Compose | Kubernetes | Complejidad adecuada para fase actual del proyecto |

---

**Fin del documento**

*Generado el 8 de febrero de 2026 por Claude Code como review técnico del proyecto NexQuant.*

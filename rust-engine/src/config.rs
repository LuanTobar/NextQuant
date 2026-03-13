use serde::Deserialize;
use std::env;
use std::time::Duration;
use tracing::{info, warn};

#[derive(Debug, Clone, PartialEq)]
pub enum DataSourceKind {
    Mock,
    Alpaca,
    Finnhub,
}

/// Configuration for a single market/exchange data source.
#[derive(Debug, Clone, Deserialize)]
pub struct MarketSourceConfig {
    pub exchange: String,      // "US", "LSE", "BME", "TSE"
    pub provider: String,      // "alpaca", "finnhub", "mock"
    pub symbols: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct Config {
    pub nats_url: String,
    pub questdb_url: String,
    pub symbols: Vec<String>,
    pub tick_interval: Duration,
    pub snapshot_interval: Duration,
    pub batch_size: usize,
    pub health_port: u16,
    pub data_source: DataSourceKind,
    pub alpaca_api_key: Option<String>,
    pub alpaca_api_secret: Option<String>,
    pub alpaca_ws_url: String,
    pub finnhub_api_key: Option<String>,
    pub finnhub_ws_url: String,
    pub bitget_ws_url: String,
    pub bitget_rest_url: String,
    /// Multi-market configuration. If empty, uses legacy single-source mode.
    pub markets: Vec<MarketSourceConfig>,
}

impl Config {
    pub fn from_env() -> Self {
        // Symbols: check SYMBOLS first, fall back to MOCK_SYMBOLS for backward compat
        let symbols_str = env::var("SYMBOLS")
            .or_else(|_| env::var("MOCK_SYMBOLS"))
            .unwrap_or_else(|_| "AAPL,GOOGL,MSFT,AMZN,TSLA".to_string());
        let symbols: Vec<String> = symbols_str.split(',').map(|s| s.trim().to_string()).collect();

        let tick_ms: u64 = env::var("TICK_INTERVAL_MS")
            .unwrap_or_else(|_| "1000".to_string())
            .parse()
            .unwrap_or(1000);

        let snapshot_ms: u64 = env::var("SNAPSHOT_INTERVAL_MS")
            .unwrap_or_else(|_| "5000".to_string())
            .parse()
            .unwrap_or(5000);

        let batch_size: usize = env::var("BATCH_SIZE")
            .unwrap_or_else(|_| "10".to_string())
            .parse()
            .unwrap_or(10);

        // Market data source selection
        let alpaca_api_key = env::var("ALPACA_API_KEY").ok().filter(|s| !s.is_empty());
        let alpaca_api_secret = env::var("ALPACA_API_SECRET").ok().filter(|s| !s.is_empty());
        let finnhub_api_key = env::var("FINNHUB_API_KEY").ok().filter(|s| !s.is_empty());

        let data_source = match env::var("MARKET_DATA_SOURCE")
            .unwrap_or_else(|_| "mock".to_string())
            .to_lowercase()
            .as_str()
        {
            "alpaca" => {
                if alpaca_api_key.is_some() && alpaca_api_secret.is_some() {
                    DataSourceKind::Alpaca
                } else {
                    warn!("MARKET_DATA_SOURCE=alpaca but ALPACA_API_KEY/SECRET not set, falling back to mock");
                    DataSourceKind::Mock
                }
            }
            "finnhub" => {
                if finnhub_api_key.is_some() {
                    DataSourceKind::Finnhub
                } else {
                    warn!("MARKET_DATA_SOURCE=finnhub but FINNHUB_API_KEY not set, falling back to mock");
                    DataSourceKind::Mock
                }
            }
            _ => DataSourceKind::Mock,
        };

        // Parse multi-market MARKETS JSON env var
        let markets = Self::parse_markets(&symbols, &data_source);

        Self {
            nats_url: env::var("NATS_URL").unwrap_or_else(|_| "nats://localhost:4222".to_string()),
            questdb_url: env::var("QUESTDB_URL").unwrap_or_else(|_| "http://localhost:9000".to_string()),
            symbols,
            tick_interval: Duration::from_millis(tick_ms),
            snapshot_interval: Duration::from_millis(snapshot_ms),
            batch_size,
            health_port: 8080,
            data_source,
            alpaca_api_key,
            alpaca_api_secret,
            alpaca_ws_url: env::var("ALPACA_WS_URL")
                .unwrap_or_else(|_| "wss://stream.data.alpaca.markets/v2/iex".to_string()),
            finnhub_api_key,
            finnhub_ws_url: env::var("FINNHUB_WS_URL")
                .unwrap_or_else(|_| "wss://ws.finnhub.io".to_string()),
            bitget_ws_url: env::var("BITGET_WS_URL")
                .unwrap_or_else(|_| "wss://ws.bitget.com/v2/ws/public".to_string()),
            bitget_rest_url: env::var("BITGET_REST_URL")
                .unwrap_or_else(|_| "https://api.bitget.com".to_string()),
            markets,
        }
    }

    /// Parse MARKETS JSON env var. If not set, synthesize from legacy config.
    fn parse_markets(legacy_symbols: &[String], legacy_source: &DataSourceKind) -> Vec<MarketSourceConfig> {
        if let Ok(markets_json) = env::var("MARKETS") {
            if !markets_json.is_empty() {
                match serde_json::from_str::<Vec<MarketSourceConfig>>(&markets_json) {
                    Ok(markets) => {
                        info!("Loaded {} market configurations from MARKETS env", markets.len());
                        for m in &markets {
                            info!("  Market {}: provider={}, symbols={:?}", m.exchange, m.provider, m.symbols);
                        }
                        return markets;
                    }
                    Err(e) => {
                        warn!("Failed to parse MARKETS JSON: {}, falling back to legacy config", e);
                    }
                }
            }
        }

        // Fallback: synthesize single market from legacy env vars
        let provider = match legacy_source {
            DataSourceKind::Alpaca => "alpaca",
            DataSourceKind::Finnhub => "finnhub",
            DataSourceKind::Mock => "mock",
        };

        vec![MarketSourceConfig {
            exchange: "US".to_string(),
            provider: provider.to_string(),
            symbols: legacy_symbols.to_vec(),
        }]
    }

    /// Check if we're in multi-market mode (more than 1 exchange configured).
    pub fn is_multi_market(&self) -> bool {
        self.markets.len() > 1
    }

    /// Get all symbols across all configured markets.
    pub fn all_symbols(&self) -> Vec<String> {
        self.markets.iter().flat_map(|m| m.symbols.clone()).collect()
    }
}

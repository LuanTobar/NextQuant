use anyhow::Result;
use async_trait::async_trait;
use chrono::Utc;
use rand::Rng;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{broadcast, Mutex};
use tracing::info;

use super::source::DataSource;
use super::types::MarketTick;

// ── Original MockDataSource ──────────────────────────────────────────────────

pub struct MockDataSource {
    prices: HashMap<String, f64>,
    symbols: Vec<String>,
    exchange: String,
}

impl MockDataSource {
    pub fn new(symbols: Vec<String>, exchange: String) -> Self {
        let mut prices = HashMap::new();

        // Realistic base prices per exchange (Feb 2025)
        let starting: &[(&str, f64)] = match exchange.as_str() {
            "US" => &[
                ("AAPL", 232.0), ("GOOGL", 199.0), ("MSFT", 410.0),
                ("AMZN", 233.0), ("TSLA", 411.0),
            ],
            "LSE" => &[
                // UK stocks (GBP pence)
                ("VOD.L", 75.0), ("BP.L", 500.0), ("HSBA.L", 650.0),
                ("AZN.L", 11000.0), ("SHEL.L", 2500.0),
            ],
            "BME" => &[
                // Spanish stocks (EUR)
                ("SAN.MC", 3.80), ("TEF.MC", 4.10), ("IBE.MC", 11.50),
                ("ITX.MC", 35.0), ("BBVA.MC", 8.50),
            ],
            "TSE" => &[
                // Japanese stocks (JPY)
                ("7203.T", 2500.0), ("6758.T", 12500.0), ("9984.T", 7000.0),
                ("8306.T", 950.0), ("6861.T", 55000.0),
            ],
            "CRYPTO" => &[
                // Crypto (USD) — Bitget format (no exchange prefix)
                ("BTCUSDT", 97000.0), ("ETHUSDT", 2700.0),
                ("SOLUSDT", 200.0), ("XRPUSDT", 2.50),
                ("ADAUSDT", 0.75),
            ],
            _ => &[],
        };

        for (sym, price) in starting {
            prices.insert(sym.to_string(), *price);
        }
        for sym in &symbols {
            prices.entry(sym.clone()).or_insert(100.0);
        }
        Self { prices, symbols, exchange }
    }

    pub fn generate_tick(&mut self, symbol: &str) -> MarketTick {
        let mut rng = rand::thread_rng();
        let current_price = self.prices.get(symbol).copied().unwrap_or(100.0);

        let volatility = 0.001;
        let drift = 0.0001;
        let change = current_price * (drift + volatility * rng.gen_range(-1.0..1.0));
        let new_price = (current_price + change).max(1.0);

        let open = current_price;
        let close = new_price;
        let high = open.max(close) * (1.0 + rng.gen_range(0.0..0.002));
        let low = open.min(close) * (1.0 - rng.gen_range(0.0..0.002));
        let volume = rng.gen_range(10_000..500_000);

        self.prices.insert(symbol.to_string(), new_price);

        MarketTick {
            timestamp: Utc::now(),
            symbol: symbol.to_string(),
            exchange: self.exchange.clone(),
            open: round2(open),
            high: round2(high),
            low: round2(low),
            close: round2(close),
            volume,
        }
    }

    pub fn generate_all_ticks(&mut self) -> Vec<MarketTick> {
        let symbols = self.symbols.clone();
        symbols.iter().map(|s| self.generate_tick(s)).collect()
    }
}

fn round2(v: f64) -> f64 {
    (v * 100.0).round() / 100.0
}

// ── DataSource trait wrapper ────────────────────────────────────────────────

/// Wrapper that implements DataSource for MockDataSource.
/// Runs a timer loop, generating ticks at the configured interval.
pub struct MockDataSourceRunner {
    inner: Arc<Mutex<MockDataSource>>,
    tick_interval: Duration,
    exchange: String,
}

impl MockDataSourceRunner {
    pub fn new(symbols: Vec<String>, tick_interval: Duration, exchange: String) -> Self {
        Self {
            inner: Arc::new(Mutex::new(MockDataSource::new(symbols, exchange.clone()))),
            tick_interval,
            exchange,
        }
    }
}

#[async_trait]
impl DataSource for MockDataSourceRunner {
    async fn run(&self, tx: broadcast::Sender<MarketTick>) -> Result<()> {
        info!("Mock data source started for {} (interval: {:?})", self.exchange, self.tick_interval);
        let mut interval = tokio::time::interval(self.tick_interval);
        loop {
            interval.tick().await;
            let mut source = self.inner.lock().await;
            let ticks = source.generate_all_ticks();
            drop(source);
            for tick in ticks {
                let _ = tx.send(tick);
            }
        }
    }

    fn name(&self) -> &str {
        "mock"
    }
}

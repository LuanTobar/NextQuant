use anyhow::{Context, Result};
use async_trait::async_trait;
use chrono::Utc;
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use std::collections::HashMap;
use std::time::Duration;
use tokio::sync::broadcast;
use tokio::time::Instant;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

use super::source::DataSource;
use super::types::MarketTick;

// ── Finnhub JSON message types ──────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct FinnhubMessage {
    #[serde(rename = "type")]
    msg_type: String,
    #[serde(default)]
    data: Option<Vec<FinnhubTrade>>,
}

#[derive(Debug, Deserialize)]
struct FinnhubTrade {
    /// Symbol
    s: String,
    /// Price
    p: f64,
    /// Unix timestamp in milliseconds
    t: u64,
    /// Volume
    v: f64,
}

// ── Trade aggregator ────────────────────────────────────────────────────────

struct TradeAccumulator {
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: u64,
    has_data: bool,
}

impl TradeAccumulator {
    fn new() -> Self {
        Self {
            open: 0.0,
            high: f64::MIN,
            low: f64::MAX,
            close: 0.0,
            volume: 0,
            has_data: false,
        }
    }

    fn add_trade(&mut self, price: f64, volume: f64) {
        if !self.has_data {
            self.open = price;
            self.high = price;
            self.low = price;
            self.has_data = true;
        }
        self.high = self.high.max(price);
        self.low = self.low.min(price);
        self.close = price;
        self.volume += volume as u64;
    }

    fn flush(&mut self, symbol: &str, exchange: &str) -> Option<MarketTick> {
        if !self.has_data {
            return None;
        }
        let tick = MarketTick {
            timestamp: Utc::now(),
            symbol: symbol.to_string(),
            exchange: exchange.to_string(),
            open: round2(self.open),
            high: round2(self.high),
            low: round2(self.low),
            close: round2(self.close),
            volume: self.volume,
        };
        // Reset for next window
        *self = Self::new();
        Some(tick)
    }
}

fn round2(v: f64) -> f64 {
    (v * 100.0).round() / 100.0
}

// ── FinnhubSource ───────────────────────────────────────────────────────────

pub struct FinnhubSource {
    ws_url: String,
    api_key: String,
    symbols: Vec<String>,
    exchange: String,
    aggregation_window: Duration,
}

impl FinnhubSource {
    pub fn new(ws_url: &str, api_key: &str, symbols: Vec<String>, exchange: &str, aggregation_window: Duration) -> Self {
        Self {
            ws_url: ws_url.to_string(),
            api_key: api_key.to_string(),
            symbols,
            exchange: exchange.to_string(),
            aggregation_window,
        }
    }

    /// Derive exchange from Finnhub symbol suffix (fallback to configured exchange).
    fn exchange_for_symbol(&self, symbol: &str) -> String {
        if symbol.starts_with("BINANCE:") || symbol.starts_with("COINBASE:") {
            "CRYPTO".to_string()
        } else if symbol.ends_with(".L") {
            "LSE".to_string()
        } else if symbol.ends_with(".MC") {
            "BME".to_string()
        } else if symbol.ends_with(".T") {
            "TSE".to_string()
        } else {
            self.exchange.clone()
        }
    }

    async fn connect_and_stream(&self, tx: &broadcast::Sender<MarketTick>) -> Result<()> {
        // Ensure URL has trailing slash before query params (Finnhub requires proper path)
        let base = if self.ws_url.ends_with('/') {
            self.ws_url.clone()
        } else {
            format!("{}/", self.ws_url)
        };
        let url = format!("{}?token={}", base, self.api_key);
        info!("Connecting to Finnhub WebSocket at {}", self.ws_url);

        let (ws_stream, _) = connect_async(&url)
            .await
            .context(format!("Failed to connect to Finnhub WebSocket at {}. Check DNS/TLS.", self.ws_url))?;

        let (mut write, mut read) = ws_stream.split();

        // Subscribe to each symbol
        for symbol in &self.symbols {
            let sub_msg = serde_json::json!({
                "type": "subscribe",
                "symbol": symbol,
            });
            write.send(Message::Text(sub_msg.to_string().into())).await?;
        }
        info!("Finnhub subscribed to symbols: {:?}", self.symbols);

        // Trade accumulators per symbol
        let mut accumulators: HashMap<String, TradeAccumulator> = HashMap::new();
        for symbol in &self.symbols {
            accumulators.insert(symbol.clone(), TradeAccumulator::new());
        }

        let mut flush_interval = tokio::time::interval(self.aggregation_window);
        let mut last_trade_time = Instant::now();

        loop {
            tokio::select! {
                msg = read.next() => {
                    match msg {
                        Some(Ok(Message::Text(text))) => {
                            self.process_trades(&text, &mut accumulators);
                            last_trade_time = Instant::now();
                        }
                        Some(Ok(Message::Ping(data))) => {
                            let _ = write.send(Message::Pong(data)).await;
                        }
                        Some(Ok(Message::Close(_))) => {
                            warn!("Finnhub WebSocket closed by server");
                            break;
                        }
                        Some(Err(e)) => {
                            error!("Finnhub WebSocket error: {}", e);
                            break;
                        }
                        None => {
                            warn!("Finnhub WebSocket stream ended");
                            break;
                        }
                        _ => {}
                    }
                }
                _ = flush_interval.tick() => {
                    // Flush accumulators into MarketTick and send
                    for (symbol, acc) in accumulators.iter_mut() {
                        let exchange = self.exchange_for_symbol(symbol);
                        if let Some(tick) = acc.flush(symbol, &exchange) {
                            info!("Finnhub tick: {} ${:.2} vol={}", tick.symbol, tick.close, tick.volume);
                            let _ = tx.send(tick);
                        }
                    }

                    // If no trades received for 30s, log warning
                    if last_trade_time.elapsed() > Duration::from_secs(30) {
                        warn!("No Finnhub trades received in 30s (market may be closed)");
                    }
                }
            }
        }

        Ok(())
    }

    fn process_trades(&self, text: &str, accumulators: &mut HashMap<String, TradeAccumulator>) {
        let msg: FinnhubMessage = match serde_json::from_str(text) {
            Ok(m) => m,
            Err(_) => return, // Ignore unparseable messages (e.g., ping responses)
        };

        if msg.msg_type != "trade" {
            return;
        }

        if let Some(trades) = msg.data {
            for trade in trades {
                if let Some(acc) = accumulators.get_mut(&trade.s) {
                    acc.add_trade(trade.p, trade.v);
                }
            }
        }
    }
}

#[async_trait]
impl DataSource for FinnhubSource {
    async fn run(&self, tx: broadcast::Sender<MarketTick>) -> Result<()> {
        let mut backoff = Duration::from_secs(1);
        let max_backoff = Duration::from_secs(60);

        loop {
            match self.connect_and_stream(&tx).await {
                Ok(_) => {
                    warn!("Finnhub stream ended, reconnecting...");
                    backoff = Duration::from_secs(1);
                }
                Err(e) => {
                    error!("Finnhub connection error: {:?}, retrying in {:?}", e, backoff);
                }
            }

            tokio::time::sleep(backoff).await;
            backoff = (backoff * 2).min(max_backoff);
        }
    }

    fn name(&self) -> &str {
        "finnhub"
    }
}

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

// ── Bitget REST candle response ─────────────────────────────────────────────

/// Bitget v2 candles response: { "code":"00000", "data":[ [ts,o,h,l,c,vol,...], ... ] }
#[derive(Debug, Deserialize)]
struct BitgetCandleResponse {
    code: String,
    #[serde(default)]
    data: Vec<Vec<String>>,
    #[serde(default)]
    msg: String,
}

// ── Bitget WebSocket message types ──────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct BitgetWsMessage {
    #[serde(default)]
    event: Option<String>,
    #[serde(default)]
    action: Option<String>,
    #[serde(default)]
    arg: Option<BitgetWsArg>,
    #[serde(default)]
    data: Option<Vec<BitgetTickerData>>,
}

#[derive(Debug, Deserialize)]
struct BitgetWsArg {
    #[serde(default, rename = "instId")]
    inst_id: String,
    #[serde(default)]
    channel: String,
}

#[derive(Debug, Deserialize)]
struct BitgetTickerData {
    /// Symbol
    #[serde(rename = "instId")]
    inst_id: String,
    /// Last price
    #[serde(rename = "lastPr")]
    last_pr: String,
    /// 24h high
    #[serde(default, rename = "high24h")]
    high_24h: String,
    /// 24h low
    #[serde(default, rename = "low24h")]
    low_24h: String,
    /// 24h base volume
    #[serde(default, rename = "baseVolume")]
    base_volume: String,
    /// 24h quote volume
    #[serde(default, rename = "quoteVolume")]
    quote_volume: String,
    /// Timestamp
    #[serde(default)]
    ts: String,
}

// ── Trade aggregator (same pattern as FinnhubSource) ────────────────────────

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

    fn add_tick(&mut self, price: f64, volume: u64) {
        if !self.has_data {
            self.open = price;
            self.high = price;
            self.low = price;
            self.has_data = true;
        }
        self.high = self.high.max(price);
        self.low = self.low.min(price);
        self.close = price;
        self.volume += volume;
    }

    fn flush(&mut self, symbol: &str, exchange: &str) -> Option<MarketTick> {
        if !self.has_data {
            return None;
        }
        let tick = MarketTick {
            timestamp: Utc::now(),
            symbol: symbol.to_string(),
            exchange: exchange.to_string(),
            open: round_price(self.open),
            high: round_price(self.high),
            low: round_price(self.low),
            close: round_price(self.close),
            volume: self.volume,
        };
        *self = Self::new();
        Some(tick)
    }
}

/// Round price to 2 decimal places for most assets, preserve more for sub-dollar.
fn round_price(v: f64) -> f64 {
    if v < 1.0 {
        (v * 100000.0).round() / 100000.0 // 5 decimals for sub-dollar (XRP, ADA)
    } else if v < 100.0 {
        (v * 1000.0).round() / 1000.0 // 3 decimals for mid-range (SOL)
    } else {
        (v * 100.0).round() / 100.0 // 2 decimals for BTC, ETH
    }
}

// ── BitgetSource ────────────────────────────────────────────────────────────

pub struct BitgetSource {
    ws_url: String,
    rest_base: String,
    symbols: Vec<String>,
    exchange: String,
    aggregation_window: Duration,
}

impl BitgetSource {
    pub fn new(
        ws_url: &str,
        rest_base: &str,
        symbols: Vec<String>,
        exchange: &str,
        aggregation_window: Duration,
    ) -> Self {
        Self {
            ws_url: ws_url.to_string(),
            rest_base: rest_base.to_string(),
            symbols,
            exchange: exchange.to_string(),
            aggregation_window,
        }
    }

    /// Bootstrap historical candles from Bitget REST API.
    /// Fetches 200 x 1-min candles per symbol so ML has data immediately on startup.
    async fn bootstrap_history(&self, tx: &broadcast::Sender<MarketTick>) -> Result<()> {
        info!(
            "Bootstrapping {} symbols with 200 x 1-min candles from Bitget REST",
            self.symbols.len()
        );

        let client = reqwest::Client::new();

        for symbol in &self.symbols {
            let url = format!(
                "{}/api/v2/spot/market/candles?symbol={}&granularity=1min&limit=200",
                self.rest_base, symbol
            );

            match client.get(&url).send().await {
                Ok(resp) => {
                    let body = resp.text().await.unwrap_or_default();
                    match serde_json::from_str::<BitgetCandleResponse>(&body) {
                        Ok(candle_resp) => {
                            if candle_resp.code != "00000" {
                                warn!(
                                    "Bitget REST error for {}: {} ({})",
                                    symbol, candle_resp.msg, candle_resp.code
                                );
                                continue;
                            }

                            let count = candle_resp.data.len();
                            // Bitget returns newest first — reverse for chronological order
                            for candle in candle_resp.data.into_iter().rev() {
                                // Format: [ts, open, high, low, close, baseVol, quoteVol]
                                if candle.len() < 6 {
                                    continue;
                                }

                                let ts_ms: i64 = candle[0].parse().unwrap_or(0);
                                let open: f64 = candle[1].parse().unwrap_or(0.0);
                                let high: f64 = candle[2].parse().unwrap_or(0.0);
                                let low: f64 = candle[3].parse().unwrap_or(0.0);
                                let close: f64 = candle[4].parse().unwrap_or(0.0);
                                let volume: u64 =
                                    candle[5].parse::<f64>().unwrap_or(0.0) as u64;

                                let timestamp = chrono::DateTime::from_timestamp_millis(ts_ms)
                                    .unwrap_or_else(|| Utc::now());

                                let tick = MarketTick {
                                    timestamp,
                                    symbol: symbol.clone(),
                                    exchange: self.exchange.clone(),
                                    open: round_price(open),
                                    high: round_price(high),
                                    low: round_price(low),
                                    close: round_price(close),
                                    volume,
                                };
                                let _ = tx.send(tick);
                            }

                            info!(
                                "Bootstrapped {} candles for {} (latest close: {})",
                                count, symbol,
                                "OK"
                            );
                        }
                        Err(e) => {
                            warn!("Failed to parse Bitget candles for {}: {}", symbol, e);
                        }
                    }
                }
                Err(e) => {
                    warn!("Failed to fetch Bitget candles for {}: {}", symbol, e);
                }
            }

            // Rate limit safety: 100ms delay between symbols
            tokio::time::sleep(Duration::from_millis(100)).await;
        }

        info!("Bootstrap complete for all symbols");
        Ok(())
    }

    /// Connect to Bitget WebSocket and stream real-time ticker data.
    async fn connect_and_stream(&self, tx: &broadcast::Sender<MarketTick>) -> Result<()> {
        info!("Connecting to Bitget WebSocket at {}", self.ws_url);

        let (ws_stream, _) = connect_async(&self.ws_url)
            .await
            .context(format!(
                "Failed to connect to Bitget WebSocket at {}",
                self.ws_url
            ))?;

        let (mut write, mut read) = ws_stream.split();

        // Subscribe to ticker channel for each symbol
        let args: Vec<serde_json::Value> = self
            .symbols
            .iter()
            .map(|sym| {
                serde_json::json!({
                    "instType": "SPOT",
                    "channel": "ticker",
                    "instId": sym
                })
            })
            .collect();

        let sub_msg = serde_json::json!({
            "op": "subscribe",
            "args": args
        });

        write
            .send(Message::Text(sub_msg.to_string().into()))
            .await?;
        info!("Bitget subscribed to ticker for: {:?}", self.symbols);

        // Trade accumulators per symbol
        let mut accumulators: HashMap<String, TradeAccumulator> = HashMap::new();
        for symbol in &self.symbols {
            accumulators.insert(symbol.clone(), TradeAccumulator::new());
        }

        let mut flush_interval = tokio::time::interval(self.aggregation_window);
        let mut last_data_time = Instant::now();

        loop {
            tokio::select! {
                msg = read.next() => {
                    match msg {
                        Some(Ok(Message::Text(text))) => {
                            let text_str: &str = &text;

                            // Bitget sends "ping" as plain text, respond with "pong"
                            if text_str.trim() == "ping" {
                                let _ = write.send(Message::Text("pong".into())).await;
                                continue;
                            }

                            self.process_ticker(text_str, &mut accumulators);
                            last_data_time = Instant::now();
                        }
                        Some(Ok(Message::Ping(data))) => {
                            let _ = write.send(Message::Pong(data)).await;
                        }
                        Some(Ok(Message::Close(_))) => {
                            warn!("Bitget WebSocket closed by server");
                            break;
                        }
                        Some(Err(e)) => {
                            error!("Bitget WebSocket error: {}", e);
                            break;
                        }
                        None => {
                            warn!("Bitget WebSocket stream ended");
                            break;
                        }
                        _ => {}
                    }
                }
                _ = flush_interval.tick() => {
                    for (symbol, acc) in accumulators.iter_mut() {
                        if let Some(tick) = acc.flush(symbol, &self.exchange) {
                            info!(
                                "Bitget tick: {} ${:.2} vol={}",
                                tick.symbol, tick.close, tick.volume
                            );
                            let _ = tx.send(tick);
                        }
                    }

                    // Warn if no data in 30s
                    if last_data_time.elapsed() > Duration::from_secs(30) {
                        warn!("No Bitget data received in 30s");
                    }
                }
            }
        }

        Ok(())
    }

    /// Process a Bitget ticker push message into the accumulators.
    fn process_ticker(&self, text: &str, accumulators: &mut HashMap<String, TradeAccumulator>) {
        let msg: BitgetWsMessage = match serde_json::from_str(text) {
            Ok(m) => m,
            Err(_) => return,
        };

        // Skip event messages (subscribe confirmations, errors)
        if msg.event.is_some() {
            if let Some(ref event) = msg.event {
                if event == "error" {
                    warn!("Bitget WS error: {:?}", text);
                } else {
                    info!("Bitget WS event: {}", event);
                }
            }
            return;
        }

        // Process ticker data
        if let Some(data) = msg.data {
            for ticker in data {
                let price: f64 = ticker.last_pr.parse().unwrap_or(0.0);
                if price <= 0.0 {
                    continue;
                }

                // Use base volume as tick volume
                let volume: u64 = ticker.base_volume.parse::<f64>().unwrap_or(0.0) as u64;

                if let Some(acc) = accumulators.get_mut(&ticker.inst_id) {
                    acc.add_tick(price, volume);
                }
            }
        }
    }
}

#[async_trait]
impl DataSource for BitgetSource {
    async fn run(&self, tx: broadcast::Sender<MarketTick>) -> Result<()> {
        // Phase 1: Bootstrap historical candles from REST API
        if let Err(e) = self.bootstrap_history(&tx).await {
            warn!("Bitget REST bootstrap failed: {:?} (continuing with WS only)", e);
        }

        // Phase 2: Stream real-time data via WebSocket with reconnection
        let mut backoff = Duration::from_secs(1);
        let max_backoff = Duration::from_secs(60);

        loop {
            match self.connect_and_stream(&tx).await {
                Ok(_) => {
                    warn!("Bitget stream ended, reconnecting...");
                    backoff = Duration::from_secs(1);
                }
                Err(e) => {
                    error!(
                        "Bitget connection error: {:?}, retrying in {:?}",
                        e, backoff
                    );
                }
            }

            tokio::time::sleep(backoff).await;
            backoff = (backoff * 2).min(max_backoff);
        }
    }

    fn name(&self) -> &str {
        "bitget"
    }
}

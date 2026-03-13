use anyhow::{Context, Result};
use async_trait::async_trait;
use chrono::DateTime;
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use std::time::Duration;
use tokio::sync::broadcast;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

use super::source::DataSource;
use super::types::MarketTick;

// ── Alpaca JSON message types ───────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct AlpacaMessage {
    #[serde(rename = "T")]
    msg_type: String,
    #[serde(default)]
    msg: Option<String>,
    // Bar fields (only present when T == "b")
    #[serde(rename = "S")]
    symbol: Option<String>,
    #[serde(rename = "o")]
    open: Option<f64>,
    #[serde(rename = "h")]
    high: Option<f64>,
    #[serde(rename = "l")]
    low: Option<f64>,
    #[serde(rename = "c")]
    close: Option<f64>,
    #[serde(rename = "v")]
    volume: Option<u64>,
    #[serde(rename = "t")]
    timestamp: Option<String>,
    // Trade fields (only present when T == "t")
    #[serde(rename = "p")]
    price: Option<f64>,
    #[serde(rename = "s")]
    size: Option<u64>,
}

// ── AlpacaSource ────────────────────────────────────────────────────────────

pub struct AlpacaSource {
    ws_url: String,
    api_key: String,
    api_secret: String,
    symbols: Vec<String>,
}

impl AlpacaSource {
    pub fn new(ws_url: &str, api_key: &str, api_secret: &str, symbols: Vec<String>) -> Self {
        Self {
            ws_url: ws_url.to_string(),
            api_key: api_key.to_string(),
            api_secret: api_secret.to_string(),
            symbols,
        }
    }

    async fn connect_and_stream(&self, tx: &broadcast::Sender<MarketTick>) -> Result<()> {
        info!("Connecting to Alpaca WebSocket at {}", self.ws_url);

        let (ws_stream, _) = connect_async(&self.ws_url)
            .await
            .context("Failed to connect to Alpaca WebSocket")?;

        let (mut write, mut read) = ws_stream.split();

        // Step 1: Read welcome message
        if let Some(msg) = read.next().await {
            let msg = msg.context("Failed to read welcome message")?;
            info!("Alpaca welcome: {}", msg);
        }

        // Step 2: Authenticate
        let auth_msg = serde_json::json!({
            "action": "auth",
            "key": self.api_key,
            "secret": self.api_secret,
        });
        write.send(Message::Text(auth_msg.to_string().into())).await?;

        // Read auth response
        if let Some(msg) = read.next().await {
            let msg = msg.context("Failed to read auth response")?;
            let text = msg.to_text().unwrap_or("");
            if text.contains("\"msg\":\"authenticated\"") {
                info!("Alpaca authenticated successfully");
            } else if text.contains("auth_failed") {
                anyhow::bail!("Alpaca authentication failed: {}", text);
            } else {
                info!("Alpaca auth response: {}", text);
            }
        }

        // Step 3: Subscribe to bars AND trades for our symbols
        let subscribe_msg = serde_json::json!({
            "action": "subscribe",
            "bars": &self.symbols,
            "trades": &self.symbols,
        });
        write.send(Message::Text(subscribe_msg.to_string().into())).await?;

        // Read subscription confirmation
        if let Some(msg) = read.next().await {
            let msg = msg.context("Failed to read subscription response")?;
            info!("Alpaca subscription confirmed: {}", msg);
        }

        info!("Alpaca streaming started for symbols: {:?}", self.symbols);

        // Step 4: Message loop
        while let Some(msg) = read.next().await {
            match msg {
                Ok(Message::Text(text)) => {
                    self.process_message(&text, tx);
                }
                Ok(Message::Ping(data)) => {
                    let _ = write.send(Message::Pong(data)).await;
                }
                Ok(Message::Close(_)) => {
                    warn!("Alpaca WebSocket closed by server");
                    break;
                }
                Err(e) => {
                    error!("Alpaca WebSocket error: {}", e);
                    break;
                }
                _ => {}
            }
        }

        Ok(())
    }

    fn process_message(&self, text: &str, tx: &broadcast::Sender<MarketTick>) {
        // Alpaca sends messages as JSON arrays: [{"T":"b","S":"AAPL",...}, ...]
        let messages: Vec<AlpacaMessage> = match serde_json::from_str(text) {
            Ok(msgs) => msgs,
            Err(e) => {
                warn!("Failed to parse Alpaca message: {} — raw: {}", e, &text[..text.len().min(200)]);
                return;
            }
        };

        for msg in messages {
            match msg.msg_type.as_str() {
                "b" => {
                    // Bar message — maps directly to MarketTick OHLCV
                    if let (Some(symbol), Some(open), Some(high), Some(low), Some(close), Some(volume), Some(ts)) =
                        (&msg.symbol, msg.open, msg.high, msg.low, msg.close, msg.volume, &msg.timestamp)
                    {
                        let timestamp = DateTime::parse_from_rfc3339(ts)
                            .map(|dt| dt.with_timezone(&chrono::Utc))
                            .unwrap_or_else(|_| chrono::Utc::now());

                        let tick = MarketTick {
                            timestamp,
                            symbol: symbol.clone(),
                            exchange: "US".to_string(),
                            open,
                            high,
                            low,
                            close,
                            volume,
                        };
                        info!("Alpaca bar: {} ${:.2} vol={}", symbol, close, volume);
                        let _ = tx.send(tick);
                    }
                }
                "t" => {
                    // Trade message — create a tick where open=high=low=close=price
                    if let (Some(symbol), Some(price), Some(size), Some(ts)) =
                        (&msg.symbol, msg.price, msg.size, &msg.timestamp)
                    {
                        let timestamp = DateTime::parse_from_rfc3339(ts)
                            .map(|dt| dt.with_timezone(&chrono::Utc))
                            .unwrap_or_else(|_| chrono::Utc::now());

                        let tick = MarketTick {
                            timestamp,
                            symbol: symbol.clone(),
                            exchange: "US".to_string(),
                            open: price,
                            high: price,
                            low: price,
                            close: price,
                            volume: size,
                        };
                        let _ = tx.send(tick);
                    }
                }
                "success" | "subscription" => {
                    // Control messages, already logged above
                }
                "error" => {
                    error!("Alpaca error: {:?}", msg.msg);
                }
                _ => {
                    // Unknown message type, ignore
                }
            }
        }
    }
}

#[async_trait]
impl DataSource for AlpacaSource {
    async fn run(&self, tx: broadcast::Sender<MarketTick>) -> Result<()> {
        let mut backoff = Duration::from_secs(1);
        let max_backoff = Duration::from_secs(60);

        loop {
            match self.connect_and_stream(&tx).await {
                Ok(_) => {
                    warn!("Alpaca stream ended cleanly, reconnecting...");
                    backoff = Duration::from_secs(1); // reset on clean disconnect
                }
                Err(e) => {
                    error!("Alpaca connection error: {}, retrying in {:?}", e, backoff);
                }
            }

            tokio::time::sleep(backoff).await;
            backoff = (backoff * 2).min(max_backoff);
        }
    }

    fn name(&self) -> &str {
        "alpaca"
    }
}

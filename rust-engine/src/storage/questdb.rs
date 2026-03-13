use anyhow::Result;
use reqwest::Client;
use tracing::{error, info};

use crate::market_data::types::MarketTick;

pub struct QuestDBClient {
    client: Client,
    base_url: String,
}

impl QuestDBClient {
    pub fn new(base_url: &str) -> Self {
        Self {
            client: Client::new(),
            base_url: base_url.to_string(),
        }
    }

    pub async fn create_tables(&self) -> Result<()> {
        let query = "CREATE TABLE IF NOT EXISTS market_data (\
            timestamp TIMESTAMP, \
            symbol SYMBOL, \
            exchange SYMBOL, \
            open DOUBLE, \
            high DOUBLE, \
            low DOUBLE, \
            close DOUBLE, \
            volume LONG\
        ) TIMESTAMP(timestamp) PARTITION BY DAY;";

        self.exec_query(query).await?;

        let signals_query = "CREATE TABLE IF NOT EXISTS ml_signals (\
            timestamp TIMESTAMP, \
            symbol SYMBOL, \
            exchange SYMBOL, \
            signal STRING, \
            current_price DOUBLE, \
            predicted_close DOUBLE, \
            confidence_low DOUBLE, \
            confidence_high DOUBLE, \
            regime STRING, \
            causal_effect DOUBLE, \
            causal_description STRING, \
            volatility DOUBLE\
        ) TIMESTAMP(timestamp) PARTITION BY DAY;";

        self.exec_query(signals_query).await?;

        // Migration: add exchange column to existing tables (no-op if already exists)
        let _ = self.exec_query("ALTER TABLE market_data ADD COLUMN exchange SYMBOL;").await;
        let _ = self.exec_query("ALTER TABLE ml_signals ADD COLUMN exchange SYMBOL;").await;

        info!("QuestDB tables created/migrated");
        Ok(())
    }

    pub async fn insert_ticks(&self, ticks: &[MarketTick]) -> Result<()> {
        if ticks.is_empty() {
            return Ok(());
        }

        let values: Vec<String> = ticks
            .iter()
            .map(|t| {
                format!(
                    "('{}', '{}', '{}', {}, {}, {}, {}, {})",
                    t.timestamp.format("%Y-%m-%dT%H:%M:%S%.6fZ"),
                    t.symbol,
                    t.exchange,
                    t.open,
                    t.high,
                    t.low,
                    t.close,
                    t.volume
                )
            })
            .collect();

        let query = format!(
            "INSERT INTO market_data (timestamp, symbol, exchange, open, high, low, close, volume) VALUES {};",
            values.join(", ")
        );

        self.exec_query(&query).await?;
        Ok(())
    }

    async fn exec_query(&self, query: &str) -> Result<()> {
        let url = format!("{}/exec", self.base_url);
        let resp = self
            .client
            .get(&url)
            .query(&[("query", query)])
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            error!("QuestDB query failed ({}): {}", status, body);
            anyhow::bail!("QuestDB query failed: {} - {}", status, body);
        }
        Ok(())
    }
}

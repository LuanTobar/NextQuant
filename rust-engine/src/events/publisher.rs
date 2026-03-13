use anyhow::Result;
use async_nats::Client;
use tracing::{info, warn};

use crate::market_data::types::{MarketSnapshot, MarketTick};

pub struct NatsPublisher {
    client: Client,
}

impl NatsPublisher {
    pub async fn connect(url: &str) -> Result<Self> {
        let client = async_nats::connect(url).await?;
        info!("Connected to NATS at {}", url);
        Ok(Self { client })
    }

    pub async fn publish_tick(&self, tick: &MarketTick) -> Result<()> {
        // Multi-market subject: market.tick.{EXCHANGE}.{SYMBOL}
        let subject = format!("market.tick.{}.{}", tick.exchange, tick.symbol);
        let payload = serde_json::to_vec(tick)?;
        self.client.publish(subject, payload.into()).await?;
        Ok(())
    }

    pub async fn publish_snapshot(&self, snapshot: &MarketSnapshot) -> Result<()> {
        let payload = serde_json::to_vec(snapshot)?;
        self.client.publish("market.snapshot".to_string(), payload.into()).await?;
        info!(
            "Published snapshot with {} ticks at {}",
            snapshot.ticks.len(),
            snapshot.timestamp
        );
        Ok(())
    }

    pub async fn publish_signal(&self, subject: &str, data: &[u8]) -> Result<()> {
        self.client.publish(subject.to_string(), data.to_vec().into()).await?;
        Ok(())
    }

    pub async fn publish_anomaly(
        &self,
        anomaly: &crate::market_data::anomaly_detector::MarketAnomaly,
    ) -> Result<()> {
        let subject = format!("market.anomaly.{}.{}", anomaly.exchange, anomaly.symbol);
        let payload = serde_json::to_vec(anomaly)?;
        self.client.publish(subject, payload.into()).await?;
        Ok(())
    }
}

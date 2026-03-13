use anyhow::Result;
use async_trait::async_trait;
use tokio::sync::broadcast;

use super::types::MarketTick;

/// Unified data source trait. All sources (mock, Alpaca, Finnhub) implement this.
/// The `run` method should loop indefinitely, sending MarketTick values into the channel.
#[async_trait]
pub trait DataSource: Send + Sync + 'static {
    /// Start producing ticks. Sends MarketTick values into the provided sender.
    /// This method should run indefinitely (spawned as a tokio task).
    async fn run(&self, tx: broadcast::Sender<MarketTick>) -> Result<()>;

    /// Human-readable name for logging.
    fn name(&self) -> &str;
}

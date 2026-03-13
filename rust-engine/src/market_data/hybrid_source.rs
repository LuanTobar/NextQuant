use anyhow::Result;
use async_trait::async_trait;
use std::time::Duration;
use tokio::sync::broadcast;
use tracing::{info, warn};

use super::market_hours::MarketSchedule;
use super::mock_source::MockDataSourceRunner;
use super::source::DataSource;
use super::types::MarketTick;

/// HybridSource wraps a real data source with automatic mock fallback.
/// - During market hours: uses the real source (Alpaca/Finnhub)
/// - Outside market hours: uses mock data
/// - On real source failure: falls back to mock, retries periodically
pub struct HybridSource {
    real_source: Box<dyn DataSource>,
    symbols: Vec<String>,
    exchange: String,
    tick_interval: Duration,
    schedule: MarketSchedule,
}

impl HybridSource {
    pub fn new(
        real_source: Box<dyn DataSource>,
        symbols: Vec<String>,
        exchange: &str,
        tick_interval: Duration,
    ) -> Self {
        let schedule = MarketSchedule::for_exchange(exchange);
        Self {
            real_source,
            symbols,
            exchange: exchange.to_string(),
            tick_interval,
            schedule,
        }
    }
}

#[async_trait]
impl DataSource for HybridSource {
    async fn run(&self, tx: broadcast::Sender<MarketTick>) -> Result<()> {
        let mock = MockDataSourceRunner::new(
            self.symbols.clone(),
            self.tick_interval,
            self.exchange.clone(),
        );
        let retry_interval = Duration::from_secs(60);

        loop {
            if self.schedule.is_open() {
                info!(
                    "Market {} is {} — starting {} real data source",
                    self.exchange,
                    self.schedule.status(),
                    self.real_source.name()
                );

                let tx_clone = tx.clone();
                let result = tokio::select! {
                    r = self.real_source.run(tx_clone) => r,
                    _ = wait_for_market_close(&self.schedule) => {
                        info!("{} market closed, switching to mock data", self.exchange);
                        Ok(())
                    }
                };

                if let Err(e) = result {
                    warn!(
                        "Real data source ({}) for {} failed: {}, falling back to mock",
                        self.real_source.name(),
                        self.exchange,
                        e
                    );
                }
            }

            // Market is closed or real source failed — use mock
            info!(
                "Market {} is {} — using mock data (retry in {:?})",
                self.exchange,
                self.schedule.status(),
                retry_interval
            );

            let mock_tx = tx.clone();
            tokio::select! {
                _ = mock.run(mock_tx) => {},
                _ = wait_for_market_open_or_timeout(&self.schedule, retry_interval) => {
                    info!("Checking if {} market opened or retrying real source...", self.exchange);
                }
            }
        }
    }

    fn name(&self) -> &str {
        "hybrid"
    }
}

/// Wait until the market closes (checks every 30 seconds)
async fn wait_for_market_close(schedule: &MarketSchedule) {
    loop {
        tokio::time::sleep(Duration::from_secs(30)).await;
        if !schedule.is_open() {
            return;
        }
    }
}

/// Wait until market opens or timeout, whichever comes first
async fn wait_for_market_open_or_timeout(schedule: &MarketSchedule, timeout: Duration) {
    let start = tokio::time::Instant::now();
    loop {
        tokio::time::sleep(Duration::from_secs(10)).await;
        if schedule.is_open() || start.elapsed() >= timeout {
            return;
        }
    }
}

//! Market Sentinel — detects price gaps and volume spikes in the tick stream.
//!
//! Publishes to `market.anomaly.{EXCHANGE}.{SYMBOL}` on NATS.

use std::collections::{HashMap, VecDeque};

use chrono::Utc;
use serde::{Deserialize, Serialize};

use crate::market_data::types::MarketTick;

const VOLUME_WINDOW: usize = 20;
const VOLUME_SPIKE_Z: f64 = 3.0;
const PRICE_GAP_THRESHOLD: f64 = 0.01; // 1% gap triggers anomaly

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketAnomaly {
    pub timestamp: String,
    pub symbol: String,
    pub exchange: String,
    /// "PRICE_GAP_UP" | "PRICE_DROP" | "VOLUME_SPIKE"
    pub anomaly_type: String,
    /// Normalized 0.0–1.0 (1.0 = extreme)
    pub severity: f64,
    pub price: f64,
    pub volume: u64,
    pub price_gap_pct: f64,
    pub volume_z_score: f64,
}

struct SymbolHistory {
    last_price: f64,
    volumes: VecDeque<f64>,
}

impl SymbolHistory {
    fn new(price: f64, volume: u64) -> Self {
        let mut vols = VecDeque::with_capacity(VOLUME_WINDOW + 1);
        vols.push_back(volume as f64);
        Self { last_price: price, volumes: vols }
    }

    fn update(&mut self, price: f64, volume: u64) {
        self.last_price = price;
        if self.volumes.len() >= VOLUME_WINDOW {
            self.volumes.pop_front();
        }
        self.volumes.push_back(volume as f64);
    }

    /// Returns (mean, std) of the rolling volume window.
    fn volume_stats(&self) -> (f64, f64) {
        let n = self.volumes.len() as f64;
        if n < 2.0 {
            return (0.0, 1.0);
        }
        let mean = self.volumes.iter().sum::<f64>() / n;
        let var = self.volumes.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (n - 1.0);
        (mean, var.sqrt().max(1.0))
    }
}

pub struct AnomalyDetector {
    history: HashMap<String, SymbolHistory>,
}

impl AnomalyDetector {
    pub fn new() -> Self {
        Self { history: HashMap::new() }
    }

    /// Check a tick for anomalies. Returns `Some(anomaly)` if one is detected.
    pub fn check(&mut self, tick: &MarketTick) -> Option<MarketAnomaly> {
        let key = format!("{}:{}", tick.exchange, tick.symbol);
        let price = tick.close;
        let volume = tick.volume;

        // First tick for this symbol — bootstrap history, no anomaly yet
        if !self.history.contains_key(&key) {
            self.history.insert(key, SymbolHistory::new(price, volume));
            return None;
        }

        // Compute metrics from existing history (borrow ends before mut borrow below)
        let (price_gap_pct, volume_z, last_price) = {
            let h = self.history.get(&key).unwrap();
            let gap = (price - h.last_price).abs() / h.last_price.max(1e-10);
            let (vol_mean, vol_std) = h.volume_stats();
            let z = (volume as f64 - vol_mean) / vol_std;
            (gap, z, h.last_price)
        };

        // Determine anomaly type and severity
        let anomaly = if price_gap_pct >= PRICE_GAP_THRESHOLD {
            let atype = if price > last_price { "PRICE_GAP_UP" } else { "PRICE_DROP" };
            // 1% gap → severity 0.20; 5% gap → severity 1.0
            let severity = (price_gap_pct / 0.05).min(1.0);
            Some((atype.to_string(), severity))
        } else if volume_z >= VOLUME_SPIKE_Z {
            // 3σ → severity 0.30; 10σ → severity 1.0
            let severity = ((volume_z - VOLUME_SPIKE_Z) / 7.0 + 0.30).min(1.0);
            Some(("VOLUME_SPIKE".to_string(), severity))
        } else {
            None
        };

        // Always update history
        self.history.get_mut(&key).unwrap().update(price, volume);

        anomaly.map(|(anomaly_type, severity)| MarketAnomaly {
            timestamp: Utc::now().to_rfc3339(),
            symbol: tick.symbol.clone(),
            exchange: tick.exchange.clone(),
            anomaly_type,
            severity,
            price,
            volume,
            price_gap_pct,
            volume_z_score: volume_z,
        })
    }
}

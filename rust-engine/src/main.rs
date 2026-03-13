mod config;
mod events;
mod market_data;
mod storage;

use anyhow::Result;
use axum::{routing::get, Router};
use chrono::Utc;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{broadcast, Mutex};
use tokio::time;
use tracing::info;

use config::Config;
use events::publisher::NatsPublisher;
use market_data::alpaca_source::AlpacaSource;
use market_data::anomaly_detector::AnomalyDetector;
use market_data::bitget_source::BitgetSource;
use market_data::finnhub_source::FinnhubSource;
use market_data::hybrid_source::HybridSource;
use market_data::mock_source::MockDataSourceRunner;
use market_data::source::DataSource;
use market_data::types::{MarketSnapshot, MarketTick};
use storage::questdb::QuestDBClient;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("nexquant_engine=info".parse()?),
        )
        .init();

    let cfg = Config::from_env();
    info!("Starting NexQuant Engine");
    info!("Markets configured: {}", cfg.markets.len());
    for m in &cfg.markets {
        info!("  {} → provider={}, symbols={:?}", m.exchange, m.provider, m.symbols);
    }
    info!("Tick interval: {:?}", cfg.tick_interval);

    // Initialize services with retry
    let questdb = QuestDBClient::new(&cfg.questdb_url);
    retry_create_tables(&questdb).await?;

    let nats = NatsPublisher::connect(&cfg.nats_url).await?;
    let nats = Arc::new(nats);

    // ── Create broadcast channel for unified tick flow ───────────────────
    let (tick_tx, _) = broadcast::channel::<MarketTick>(4096);

    // ── Spawn one data source per configured market ─────────────────────
    let mut source_handles = Vec::new();

    for market in &cfg.markets {
        let source: Box<dyn DataSource> = match market.provider.as_str() {
            "alpaca" => {
                if let (Some(key), Some(secret)) = (&cfg.alpaca_api_key, &cfg.alpaca_api_secret) {
                    let alpaca = AlpacaSource::new(
                        &cfg.alpaca_ws_url,
                        key,
                        secret,
                        market.symbols.clone(),
                    );
                    Box::new(HybridSource::new(
                        Box::new(alpaca),
                        market.symbols.clone(),
                        &market.exchange,
                        cfg.tick_interval,
                    ))
                } else {
                    info!("Alpaca keys not set for {}, using mock", market.exchange);
                    Box::new(MockDataSourceRunner::new(
                        market.symbols.clone(),
                        cfg.tick_interval,
                        market.exchange.clone(),
                    ))
                }
            }
            "finnhub" => {
                if let Some(key) = &cfg.finnhub_api_key {
                    let finnhub = FinnhubSource::new(
                        &cfg.finnhub_ws_url,
                        key,
                        market.symbols.clone(),
                        &market.exchange,
                        cfg.tick_interval,
                    );
                    Box::new(HybridSource::new(
                        Box::new(finnhub),
                        market.symbols.clone(),
                        &market.exchange,
                        cfg.tick_interval,
                    ))
                } else {
                    info!("Finnhub key not set for {}, using mock", market.exchange);
                    Box::new(MockDataSourceRunner::new(
                        market.symbols.clone(),
                        cfg.tick_interval,
                        market.exchange.clone(),
                    ))
                }
            }
            "bitget" => {
                let bitget = BitgetSource::new(
                    &cfg.bitget_ws_url,
                    &cfg.bitget_rest_url,
                    market.symbols.clone(),
                    &market.exchange,
                    cfg.tick_interval,
                );
                Box::new(HybridSource::new(
                    Box::new(bitget),
                    market.symbols.clone(),
                    &market.exchange,
                    cfg.tick_interval,
                ))
            }
            _ => {
                Box::new(MockDataSourceRunner::new(
                    market.symbols.clone(),
                    cfg.tick_interval,
                    market.exchange.clone(),
                ))
            }
        };

        let exchange_name = market.exchange.clone();
        let source_name = source.name().to_string();
        info!("Spawning {} source for {} exchange", source_name, exchange_name);

        let source_tx = tick_tx.clone();
        let handle = tokio::spawn(async move {
            if let Err(e) = source.run(source_tx).await {
                tracing::error!("{} data source fatal error: {}", exchange_name, e);
            }
        });
        source_handles.push(handle);
    }

    info!("Spawned {} market data sources", source_handles.len());

    // ── Spawn health check server ────────────────────────────────────────
    let health_handle = tokio::spawn(run_health_server(cfg.health_port));

    // ── Tick buffer for QuestDB batch writes ─────────────────────────────
    let tick_buffer: Arc<Mutex<Vec<MarketTick>>> = Arc::new(Mutex::new(Vec::new()));

    // ── Spawn tick relay: channel → NATS publish + QuestDB buffer ────────
    let mut tick_rx = tick_tx.subscribe();
    let tick_nats = nats.clone();
    let tick_buf = tick_buffer.clone();
    let tick_handle = tokio::spawn(async move {
        loop {
            match tick_rx.recv().await {
                Ok(tick) => {
                    // Publish to NATS
                    if let Err(e) = tick_nats.publish_tick(&tick).await {
                        tracing::warn!("Failed to publish tick: {}", e);
                    }
                    // Buffer for QuestDB
                    tick_buf.lock().await.push(tick);
                }
                Err(broadcast::error::RecvError::Lagged(n)) => {
                    tracing::warn!("Tick receiver lagged, skipped {} messages", n);
                }
                Err(broadcast::error::RecvError::Closed) => {
                    tracing::warn!("Tick channel closed");
                    break;
                }
            }
        }
    });

    // ── Spawn snapshot aggregator ────────────────────────────────────────
    let mut snap_rx = tick_tx.subscribe();
    let snap_nats = nats.clone();
    let snapshot_interval = cfg.snapshot_interval;
    let snapshot_handle = tokio::spawn(async move {
        // Key by "EXCHANGE:SYMBOL" for multi-market dedup
        let mut latest_ticks: HashMap<String, MarketTick> = HashMap::new();
        let mut interval = time::interval(snapshot_interval);
        loop {
            tokio::select! {
                result = snap_rx.recv() => {
                    match result {
                        Ok(tick) => {
                            let key = format!("{}:{}", tick.exchange, tick.symbol);
                            latest_ticks.insert(key, tick);
                        }
                        Err(broadcast::error::RecvError::Lagged(n)) => {
                            tracing::warn!("Snapshot receiver lagged, skipped {} messages", n);
                        }
                        Err(broadcast::error::RecvError::Closed) => break,
                    }
                }
                _ = interval.tick() => {
                    if !latest_ticks.is_empty() {
                        let snapshot = MarketSnapshot {
                            timestamp: Utc::now(),
                            ticks: latest_ticks.values().cloned().collect(),
                        };
                        if let Err(e) = snap_nats.publish_snapshot(&snapshot).await {
                            tracing::warn!("Failed to publish snapshot: {}", e);
                        }
                        latest_ticks.clear();
                    }
                }
            }
        }
    });

    // ── Spawn anomaly detector (Market Sentinel) ─────────────────────────
    let mut anomaly_rx = tick_tx.subscribe();
    let anomaly_nats = nats.clone();
    let anomaly_handle = tokio::spawn(async move {
        let mut detector = AnomalyDetector::new();
        loop {
            match anomaly_rx.recv().await {
                Ok(tick) => {
                    if let Some(anomaly) = detector.check(&tick) {
                        tracing::info!(
                            "Anomaly detected: {} {} {:.2}% severity={:.2}",
                            anomaly.symbol, anomaly.anomaly_type,
                            anomaly.price_gap_pct * 100.0, anomaly.severity,
                        );
                        if let Err(e) = anomaly_nats.publish_anomaly(&anomaly).await {
                            tracing::warn!("Failed to publish anomaly: {}", e);
                        }
                    }
                }
                Err(broadcast::error::RecvError::Lagged(n)) => {
                    tracing::warn!("Anomaly receiver lagged, skipped {} ticks", n);
                }
                Err(broadcast::error::RecvError::Closed) => break,
            }
        }
    });

    // ── Spawn QuestDB batch writer ───────────────────────────────────────
    let db_buf = tick_buffer.clone();
    let batch_size = cfg.batch_size;
    let db_handle = tokio::spawn(async move {
        let mut interval = time::interval(std::time::Duration::from_secs(2));
        loop {
            interval.tick().await;
            let mut buf = db_buf.lock().await;
            if buf.len() >= batch_size {
                let batch: Vec<MarketTick> = buf.drain(..).collect();
                drop(buf);
                if let Err(e) = questdb.insert_ticks(&batch).await {
                    tracing::warn!("Failed to insert batch: {}", e);
                } else {
                    info!("Inserted {} ticks to QuestDB", batch.len());
                }
            }
        }
    });

    info!("NexQuant Engine running. Press Ctrl+C to stop.");

    tokio::select! {
        _ = tokio::signal::ctrl_c() => {
            info!("Shutting down...");
        }
        r = health_handle => { r??; }
        r = tick_handle => { r?; }
        r = snapshot_handle => { r?; }
        r = db_handle => { r?; }
        r = anomaly_handle => { r?; }
    }

    Ok(())
}

async fn retry_create_tables(questdb: &QuestDBClient) -> Result<()> {
    for attempt in 1..=10 {
        match questdb.create_tables().await {
            Ok(_) => return Ok(()),
            Err(e) => {
                tracing::warn!("QuestDB not ready (attempt {}): {}", attempt, e);
                time::sleep(std::time::Duration::from_secs(2)).await;
            }
        }
    }
    anyhow::bail!("Failed to connect to QuestDB after 10 attempts")
}

async fn run_health_server(port: u16) -> Result<()> {
    let app = Router::new().route("/health", get(|| async { "OK" }));
    let addr = format!("0.0.0.0:{}", port);
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    info!("Health server listening on {}", addr);
    axum::serve(listener, app).await?;
    Ok(())
}

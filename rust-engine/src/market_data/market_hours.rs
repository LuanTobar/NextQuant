use chrono::{Datelike, NaiveTime, Utc, Weekday};
use chrono_tz::Tz;

/// A trading session window (e.g., morning session, afternoon session).
#[derive(Debug, Clone)]
pub struct TradingSession {
    pub open: NaiveTime,
    pub close: NaiveTime,
}

/// Market schedule for a specific exchange with timezone and trading sessions.
/// Supports markets with lunch breaks (e.g., TSE has 2 sessions).
#[derive(Debug, Clone)]
pub struct MarketSchedule {
    pub exchange: String,
    pub timezone: Tz,
    pub sessions: Vec<TradingSession>,
}

impl MarketSchedule {
    pub fn is_open(&self) -> bool {
        // Crypto markets are always open (24/7/365)
        if self.exchange == "CRYPTO" {
            return true;
        }

        let now = Utc::now().with_timezone(&self.timezone);
        let day = now.weekday();

        // Weekend check (traditional markets closed Sat/Sun)
        if matches!(day, Weekday::Sat | Weekday::Sun) {
            return false;
        }

        let time = now.time();
        self.sessions.iter().any(|s| time >= s.open && time < s.close)
    }

    pub fn status(&self) -> &'static str {
        if self.is_open() { "OPEN" } else { "CLOSED" }
    }

    /// NYSE/NASDAQ: Mon-Fri, 9:30-16:00 America/New_York
    pub fn us() -> Self {
        Self {
            exchange: "US".to_string(),
            timezone: "America/New_York".parse().unwrap(),
            sessions: vec![TradingSession {
                open: NaiveTime::from_hms_opt(9, 30, 0).unwrap(),
                close: NaiveTime::from_hms_opt(16, 0, 0).unwrap(),
            }],
        }
    }

    /// London Stock Exchange: Mon-Fri, 8:00-16:30 Europe/London
    pub fn lse() -> Self {
        Self {
            exchange: "LSE".to_string(),
            timezone: "Europe/London".parse().unwrap(),
            sessions: vec![TradingSession {
                open: NaiveTime::from_hms_opt(8, 0, 0).unwrap(),
                close: NaiveTime::from_hms_opt(16, 30, 0).unwrap(),
            }],
        }
    }

    /// Bolsa de Madrid (BME): Mon-Fri, 9:00-17:30 Europe/Madrid
    pub fn bme() -> Self {
        Self {
            exchange: "BME".to_string(),
            timezone: "Europe/Madrid".parse().unwrap(),
            sessions: vec![TradingSession {
                open: NaiveTime::from_hms_opt(9, 0, 0).unwrap(),
                close: NaiveTime::from_hms_opt(17, 30, 0).unwrap(),
            }],
        }
    }

    /// Tokyo Stock Exchange: Mon-Fri, 9:00-11:30 + 12:30-15:00 Asia/Tokyo
    pub fn tse() -> Self {
        Self {
            exchange: "TSE".to_string(),
            timezone: "Asia/Tokyo".parse().unwrap(),
            sessions: vec![
                TradingSession {
                    open: NaiveTime::from_hms_opt(9, 0, 0).unwrap(),
                    close: NaiveTime::from_hms_opt(11, 30, 0).unwrap(),
                },
                TradingSession {
                    open: NaiveTime::from_hms_opt(12, 30, 0).unwrap(),
                    close: NaiveTime::from_hms_opt(15, 0, 0).unwrap(),
                },
            ],
        }
    }

    /// Crypto markets: 24/7/365 — always open
    pub fn crypto() -> Self {
        Self {
            exchange: "CRYPTO".to_string(),
            timezone: "UTC".parse().unwrap(),
            sessions: vec![TradingSession {
                open: NaiveTime::from_hms_opt(0, 0, 0).unwrap(),
                close: NaiveTime::from_hms_opt(23, 59, 59).unwrap(),
            }],
        }
    }

    /// Get schedule by exchange code
    pub fn for_exchange(exchange: &str) -> Self {
        match exchange {
            "US" => Self::us(),
            "LSE" => Self::lse(),
            "BME" => Self::bme(),
            "TSE" => Self::tse(),
            "CRYPTO" => Self::crypto(),
            _ => Self::us(), // fallback to US
        }
    }
}

/// Legacy function — checks if the US market is open.
/// Kept for backward compatibility.
pub fn is_market_open() -> bool {
    MarketSchedule::us().is_open()
}

/// Legacy function — returns US market status string.
pub fn market_status() -> &'static str {
    if is_market_open() { "OPEN" } else { "CLOSED" }
}

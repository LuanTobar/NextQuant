const QUESTDB_URL = process.env.QUESTDB_URL || 'http://localhost:9000';

/**
 * Sanitize symbol input to prevent SQL injection.
 * Allows only alphanumeric, dots, colons, underscores, hyphens.
 */
function sanitizeSymbol(symbol: string): string {
  return symbol.replace(/[^a-zA-Z0-9.:_-]/g, '');
}

/** Validate limit is a finite positive integer */
function sanitizeLimit(limit: number): number {
  const n = Math.floor(Math.abs(limit));
  if (!Number.isFinite(n) || n <= 0) return 100;
  return Math.min(n, 10000);
}

export async function queryQuestDB<T>(sql: string): Promise<T[]> {
  const url = `${QUESTDB_URL}/exec?query=${encodeURIComponent(sql)}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`QuestDB query failed: ${res.status}`);
  }
  const data = await res.json();
  if (!data.dataset) return [];

  const columns: string[] = data.columns.map((c: { name: string }) => c.name);
  return data.dataset.map((row: unknown[]) => {
    const obj: Record<string, unknown> = {};
    columns.forEach((col, i) => {
      obj[col] = row[i];
    });
    return obj as T;
  });
}

export async function getLatestPrices() {
  return queryQuestDB<{
    symbol: string;
    exchange: string;
    close: number;
    volume: number;
    timestamp: string;
  }>(
    `SELECT symbol, exchange, close, volume, timestamp
     FROM market_data
     LATEST ON timestamp PARTITION BY symbol`
  );
}

export async function getPriceHistory(symbol: string, limit = 100) {
  const safe = sanitizeSymbol(symbol);
  const safeLimit = sanitizeLimit(limit);
  return queryQuestDB<{
    timestamp: string;
    close: number;
    volume: number;
  }>(
    `SELECT timestamp, close, volume
     FROM market_data
     WHERE symbol = '${safe}'
     ORDER BY timestamp DESC
     LIMIT ${safeLimit}`
  );
}

export async function getLatestSignals() {
  return queryQuestDB<{
    timestamp: string;
    symbol: string;
    exchange: string;
    signal: string;
    current_price: number;
    predicted_close: number;
    confidence_low: number;
    confidence_high: number;
    regime: string;
    causal_effect: number;
    causal_description: string;
    volatility: number;
  }>(
    `SELECT timestamp, symbol, exchange, signal, current_price, predicted_close,
            confidence_low, confidence_high, regime, causal_effect,
            causal_description, volatility
     FROM ml_signals
     LATEST ON timestamp PARTITION BY symbol`
  );
}

export async function getSignalHistory(symbol: string, limit = 50) {
  const safe = sanitizeSymbol(symbol);
  const safeLimit = sanitizeLimit(limit);
  return queryQuestDB<{
    timestamp: string;
    symbol: string;
    signal: string;
    current_price: number;
    predicted_close: number;
    confidence_low: number;
    confidence_high: number;
    regime: string;
    causal_effect: number;
    causal_description: string;
    volatility: number;
  }>(
    `SELECT timestamp, symbol, signal, current_price, predicted_close,
            confidence_low, confidence_high, regime, causal_effect,
            causal_description, volatility
     FROM ml_signals
     WHERE symbol = '${safe}'
     ORDER BY timestamp DESC
     LIMIT ${safeLimit}`
  );
}

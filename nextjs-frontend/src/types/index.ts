export interface MarketTick {
  timestamp: string;
  symbol: string;
  exchange: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MLSignal {
  timestamp: string;
  symbol: string;
  exchange: string;
  current_price: number;
  signal: 'BUY' | 'SELL' | 'HOLD';
  causal_effect: number;
  causal_description: string;
  predicted_close: number;
  confidence_low: number;
  confidence_high: number;
  regime: 'LOW_VOL' | 'MEDIUM_VOL' | 'HIGH_VOL';
  regime_probabilities: Record<string, number>;
  volatility: number;
}

export interface PortfolioMetrics {
  total_value: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  positions: Position[];
  sharpe_ratio: number;
  max_drawdown: number;
}

export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  pnl: number;
  pnl_pct: number;
  weight: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

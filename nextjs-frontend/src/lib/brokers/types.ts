/**
 * Broker integration types.
 *
 * Defines the common interface that every broker client must implement,
 * plus shared request/response types for orders, positions, and account info.
 *
 * Adding a new broker only requires implementing BrokerClient.
 */

export type OrderSide = 'buy' | 'sell';
export type OrderType = 'market' | 'limit';
export type TimeInForce = 'day' | 'gtc' | 'ioc' | 'fok';

// ── Order types ──────────────────────────────────────────────

export interface OrderRequest {
  symbol: string;        // e.g. "AAPL" for Alpaca, "BTCUSDT" for Bitget
  side: OrderSide;
  quantity: number;
  type: OrderType;
  timeInForce?: TimeInForce;
  limitPrice?: number;   // required when type = 'limit'
}

export interface OrderResponse {
  brokerId: string;      // broker's order ID
  symbol: string;
  side: OrderSide;
  quantity: number;
  type: OrderType;
  status: string;        // normalized: 'new' | 'partially_filled' | 'filled' | 'cancelled' | 'rejected'
  filledQty?: number;
  filledAvgPrice?: number;
  createdAt: string;
  raw?: Record<string, unknown>;
}

// ── Account types ────────────────────────────────────────────

export interface AccountInfo {
  equity: number;
  buyingPower: number;
  cash: number;
  currency: string;
  raw?: Record<string, unknown>;
}

// ── Position types ───────────────────────────────────────────

export interface Position {
  symbol: string;
  quantity: number;
  avgEntryPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPl: number;
  unrealizedPlPct: number;
  side: 'long' | 'short';
}

// ── Order history params ─────────────────────────────────────

export interface OrderHistoryParams {
  limit?: number;
  symbol?: string;
  since?: string;        // ISO timestamp
}

// ── Cancel response ──────────────────────────────────────────

export interface CancelResult {
  success: boolean;
  message: string;
}

// ── Broker client interface ──────────────────────────────────

/**
 * Every broker client implements this interface.
 * Constructed with decrypted API credentials.
 *
 * To add a new broker (e.g. Binance, Interactive Brokers):
 *   1. Create src/lib/brokers/newbroker.ts implementing BrokerClient
 *   2. Add the broker type to Prisma enum BrokerType
 *   3. Add a case in the factory (index.ts)
 */
export interface BrokerClient {
  broker: string;

  // ── Orders ──
  placeOrder(req: OrderRequest): Promise<OrderResponse>;
  getOrder(brokerId: string): Promise<OrderResponse>;
  cancelOrder(brokerId: string): Promise<CancelResult>;
  getOrderHistory(params?: OrderHistoryParams): Promise<OrderResponse[]>;

  // ── Positions ──
  getPositions(): Promise<Position[]>;
  closePosition(symbol: string, quantity?: number): Promise<OrderResponse>;

  // ── Account ──
  getAccount(): Promise<AccountInfo>;
}

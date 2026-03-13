/**
 * Alpaca Markets broker client — full lifecycle.
 *
 * Authentication: simple API key headers
 *   APCA-API-KEY-ID + APCA-API-SECRET-KEY
 *
 * Environments:
 *   paper → https://paper-api.alpaca.markets
 *   live  → https://api.alpaca.markets
 *
 * REST API docs: https://docs.alpaca.markets/reference
 */

import type {
  BrokerClient,
  OrderRequest,
  OrderResponse,
  OrderHistoryParams,
  CancelResult,
  AccountInfo,
  Position,
} from './types';

const ALPACA_URLS = {
  paper: 'https://paper-api.alpaca.markets',
  live: 'https://api.alpaca.markets',
} as const;

interface AlpacaConfig {
  apiKey: string;
  apiSecret: string;
  environment: 'paper' | 'live';
}

export class AlpacaClient implements BrokerClient {
  broker = 'ALPACA';
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(config: AlpacaConfig) {
    this.baseUrl = ALPACA_URLS[config.environment];
    this.headers = {
      'APCA-API-KEY-ID': config.apiKey,
      'APCA-API-SECRET-KEY': config.apiSecret,
      'Content-Type': 'application/json',
    };
  }

  // ── HTTP layer ─────────────────────────────────────────────

  private async fetch<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { ...this.headers, ...(init?.headers || {}) },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        `Alpaca error (${res.status}): ${(err as Record<string, string>).message || res.statusText}`
      );
    }

    // Some DELETE endpoints return 204 no content
    if (res.status === 204) return {} as T;

    return res.json() as Promise<T>;
  }

  /**
   * Normalize Alpaca order status to our standard.
   */
  private normalizeStatus(status: string): string {
    const map: Record<string, string> = {
      accepted: 'new',
      new: 'new',
      pending_new: 'new',
      partially_filled: 'partially_filled',
      filled: 'filled',
      done_for_day: 'filled',
      canceled: 'cancelled',
      expired: 'cancelled',
      replaced: 'cancelled',
      rejected: 'rejected',
    };
    return map[status] || status;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private toOrderResponse(data: any): OrderResponse {
    return {
      brokerId: data.id,
      symbol: data.symbol,
      side: data.side,
      quantity: Number(data.qty),
      type: data.type,
      status: this.normalizeStatus(data.status),
      filledQty: data.filled_qty ? Number(data.filled_qty) : undefined,
      filledAvgPrice: data.filled_avg_price ? Number(data.filled_avg_price) : undefined,
      createdAt: data.created_at,
      raw: data,
    };
  }

  // ── Orders ─────────────────────────────────────────────────

  /**
   * Place an order.
   * POST /v2/orders
   */
  async placeOrder(req: OrderRequest): Promise<OrderResponse> {
    const body: Record<string, unknown> = {
      symbol: req.symbol,
      qty: String(req.quantity),
      side: req.side,
      type: req.type,
      time_in_force: req.timeInForce || 'day',
    };

    if (req.type === 'limit' && req.limitPrice) {
      body.limit_price = String(req.limitPrice);
    }

    const data = await this.fetch('/v2/orders', {
      method: 'POST',
      body: JSON.stringify(body),
    });

    return this.toOrderResponse(data);
  }

  /**
   * Get a specific order.
   * GET /v2/orders/{id}
   */
  async getOrder(brokerId: string): Promise<OrderResponse> {
    const data = await this.fetch(`/v2/orders/${brokerId}`);
    return this.toOrderResponse(data);
  }

  /**
   * Cancel a pending order.
   * DELETE /v2/orders/{id}
   */
  async cancelOrder(brokerId: string): Promise<CancelResult> {
    try {
      await this.fetch(`/v2/orders/${brokerId}`, { method: 'DELETE' });
      return { success: true, message: 'Order cancelled' };
    } catch (error) {
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Cancel failed',
      };
    }
  }

  /**
   * Get order history (closed/filled orders).
   * GET /v2/orders?status=closed
   */
  async getOrderHistory(params?: OrderHistoryParams): Promise<OrderResponse[]> {
    const qs: string[] = ['status=closed'];
    if (params?.limit) qs.push(`limit=${params.limit}`);
    if (params?.symbol) qs.push(`symbols=${params.symbol}`);
    if (params?.since) qs.push(`after=${params.since}`);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = await this.fetch<any[]>(`/v2/orders?${qs.join('&')}`);
    return data.map((o) => this.toOrderResponse(o));
  }

  // ── Positions ──────────────────────────────────────────────

  /**
   * Get all open positions.
   * GET /v2/positions
   */
  async getPositions(): Promise<Position[]> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = await this.fetch<any[]>('/v2/positions');

    return data.map((p) => {
      const qty = Math.abs(Number(p.qty));
      const currentPrice = Number(p.current_price);
      const avgEntryPrice = Number(p.avg_entry_price);
      const marketValue = Number(p.market_value);
      const unrealizedPl = Number(p.unrealized_pl);

      return {
        symbol: p.symbol as string,
        quantity: qty,
        avgEntryPrice,
        currentPrice,
        marketValue,
        unrealizedPl,
        unrealizedPlPct: avgEntryPrice > 0
          ? ((currentPrice - avgEntryPrice) / avgEntryPrice) * 100
          : 0,
        side: Number(p.qty) >= 0 ? 'long' as const : 'short' as const,
      };
    });
  }

  /**
   * Close a position (full or partial).
   * DELETE /v2/positions/{symbol}
   */
  async closePosition(symbol: string, quantity?: number): Promise<OrderResponse> {
    const qs = quantity ? `?qty=${quantity}` : '';
    const data = await this.fetch(`/v2/positions/${encodeURIComponent(symbol)}${qs}`, {
      method: 'DELETE',
    });
    return this.toOrderResponse(data);
  }

  // ── Account ────────────────────────────────────────────────

  /**
   * Get account info.
   * GET /v2/account
   */
  async getAccount(): Promise<AccountInfo> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = await this.fetch<any>('/v2/account');

    return {
      equity: Number(data.equity),
      buyingPower: Number(data.buying_power),
      cash: Number(data.cash),
      currency: data.currency || 'USD',
      raw: data,
    };
  }
}

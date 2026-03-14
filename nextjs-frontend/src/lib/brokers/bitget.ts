/**
 * Bitget exchange broker client — full lifecycle.
 *
 * Authentication: HMAC-SHA256 request signing
 *   prehash = timestamp + METHOD + requestPath + body
 *   signature = base64( HMAC-SHA256( prehash, apiSecret ) )
 *
 * Headers: ACCESS-KEY, ACCESS-SIGN, ACCESS-TIMESTAMP, ACCESS-PASSPHRASE
 *
 * Spot API v2 docs: https://www.bitget.com/api-doc/spot/trade/place-order
 */

import crypto from 'crypto';
import type {
  BrokerClient,
  OrderRequest,
  OrderResponse,
  OrderHistoryParams,
  CancelResult,
  AccountInfo,
  Position,
} from './types';

const BITGET_BASE = 'https://api.bitget.com';

interface BitgetConfig {
  apiKey: string;
  apiSecret: string;
  passphrase: string;
  /** When true, uses Bitget Futures (mix) API — required for simulated/demo trading keys */
  simulated?: boolean;
}

// ── Futures (mix) response types ────────────────────────────

interface BitgetMixAccount {
  marginCoin: string;
  equity?: string;        // present in some API versions
  usdtEquity?: string;   // present in others
  available?: string;
  crossedMaxAvailable?: string;
  unrealizedPL?: string;
}

interface BitgetMixPosition {
  symbol: string;
  holdSide: string;
  total: string;
  available: string;
  openPriceAvg: string;
  markPrice: string;
  unrealizedPL: string;
  marginCoin: string;
  marginMode: string;  // 'crossed' | 'isolated'
}

// ── Internal Bitget response types ─────────────────────────

interface BitgetAsset {
  coin: string;
  available: string;
  frozen: string;
  uTime?: string;
}

interface BitgetOrderInfo {
  orderId: string;
  clientOid?: string;
  symbol: string;
  side: string;
  orderType: string;
  size: string;
  price: string;
  status: string;           // 'live' | 'partially_filled' | 'filled' | 'cancelled'
  baseVolume?: string;       // filled quantity (base)
  quoteVolume?: string;      // filled quantity (quote)
  priceAvg?: string;         // average fill price
  cTime: string;             // created time (ms)
  uTime?: string;
  fee?: string;
  feeCcy?: string;
  force?: string;
}

interface BitgetTicker {
  symbol: string;
  lastPr: string;
  askPr?: string;
  bidPr?: string;
  high24h?: string;
  low24h?: string;
  change24h?: string;
  baseVolume?: string;
  quoteVolume?: string;
  ts: string;
}

/**
 * Known base-asset precision (max decimals for quantity/size) on Bitget spot.
 * Bitget returns error 40808 "checkBDScale" when size has more decimals than allowed.
 * We truncate (floor) instead of rounding to avoid exceeding available balance.
 */
const QUANTITY_PRECISION: Record<string, number> = {
  BTCUSDT: 6,
  ETHUSDT: 4,
  SOLUSDT: 4,
  XRPUSDT: 2,
  DOGEUSDT: 2,
  ADAUSDT: 2,
  MANAUSDT: 2,
  BNBUSDT: 5,
  AVAXUSDT: 4,
  DOTUSDT: 4,
  MATICUSDT: 2,
  LINKUSDT: 4,
  LTCUSDT: 5,
};

const DEFAULT_PRECISION = 4;

function truncateQuantity(symbol: string, qty: number): number {
  const decimals = QUANTITY_PRECISION[symbol] ?? DEFAULT_PRECISION;
  const factor = 10 ** decimals;
  return Math.floor(qty * factor) / factor;
}

export class BitgetClient implements BrokerClient {
  broker = 'BITGET';
  private apiKey: string;
  private apiSecret: string;
  private passphrase: string;
  private simulated: boolean;

  constructor(config: BitgetConfig) {
    this.apiKey = config.apiKey;
    this.apiSecret = config.apiSecret;
    this.passphrase = config.passphrase;
    this.simulated = config.simulated ?? false;
  }

  // ── Signing ────────────────────────────────────────────────

  private sign(
    timestamp: string,
    method: string,
    requestPath: string,
    body: string = ''
  ): string {
    const prehash = timestamp + method.toUpperCase() + requestPath + body;
    return crypto
      .createHmac('sha256', this.apiSecret)
      .update(prehash)
      .digest('base64');
  }

  // ── HTTP layer ─────────────────────────────────────────────

  private async request<T>(
    method: string,
    path: string,
    body?: Record<string, unknown>
  ): Promise<T> {
    const timestamp = Date.now().toString();
    const bodyStr = body ? JSON.stringify(body) : '';
    const signature = this.sign(timestamp, method, path, bodyStr);

    const headers: Record<string, string> = {
      'ACCESS-KEY': this.apiKey,
      'ACCESS-SIGN': signature,
      'ACCESS-TIMESTAMP': timestamp,
      'ACCESS-PASSPHRASE': this.passphrase,
      'Content-Type': 'application/json',
      locale: 'en-US',
      ...(this.simulated ? { paptrading: '1' } : {}),
    };

    const res = await fetch(`${BITGET_BASE}${path}`, {
      method,
      headers,
      ...(bodyStr ? { body: bodyStr } : {}),
    });

    const data = await res.json();

    // Bitget wraps: { code: "00000", msg: "success", data: ... }
    if (data.code !== '00000') {
      throw new Error(
        `Bitget API error (${data.code}): ${data.msg || 'Unknown error'}`
      );
    }

    return data.data as T;
  }

  /**
   * Public endpoint — no auth needed. Fetch current price for a symbol.
   */
  private async getTickerPrice(symbol: string): Promise<number> {
    const res = await fetch(
      `${BITGET_BASE}/api/v2/spot/market/tickers?symbol=${symbol}`
    );
    const data = await res.json();
    if (data.code !== '00000' || !data.data?.length) return 0;
    return Number((data.data[0] as BitgetTicker).lastPr) || 0;
  }

  /**
   * Normalize Bitget order status to our standard format.
   */
  private normalizeStatus(bgStatus: string): string {
    const map: Record<string, string> = {
      init: 'new',
      new: 'new',
      live: 'new',
      partially_filled: 'partially_filled',
      filled: 'filled',
      cancelled: 'cancelled',
      canceled: 'cancelled',
    };
    return map[bgStatus.toLowerCase()] || bgStatus;
  }

  /**
   * Convert a Bitget order info object to our OrderResponse.
   */
  private toOrderResponse(o: BitgetOrderInfo): OrderResponse {
    return {
      brokerId: o.orderId,
      symbol: o.symbol,
      side: o.side.toLowerCase() as 'buy' | 'sell',
      quantity: Number(o.size),
      type: o.orderType === 'limit' ? 'limit' : 'market',
      status: this.normalizeStatus(o.status),
      filledQty: o.baseVolume ? Number(o.baseVolume) : undefined,
      filledAvgPrice: o.priceAvg ? Number(o.priceAvg) : undefined,
      createdAt: new Date(Number(o.cTime)).toISOString(),
      raw: o as unknown as Record<string, unknown>,
    };
  }

  // ── Orders ─────────────────────────────────────────────────

  /**
   * Place a spot order.
   * POST /api/v2/spot/trade/place-order
   */
  async placeOrder(req: OrderRequest): Promise<OrderResponse> {
    // Truncate quantity to Bitget's allowed decimal precision for this symbol
    const truncatedQty = truncateQuantity(req.symbol, req.quantity);

    let data: { orderId: string; clientOid?: string };

    if (this.simulated) {
      // Futures (mix) order — tradeSide: open for buy, close for sell
      const body: Record<string, unknown> = {
        symbol: req.symbol,
        productType: 'USDT-FUTURES',
        marginMode: 'crossed',
        marginCoin: 'USDT',
        size: String(truncatedQty),
        side: req.side,
        tradeSide: req.side === 'buy' ? 'open' : 'close',
        orderType: req.type,
        force: req.timeInForce || 'gtc',
      };
      if (req.type === 'limit' && req.limitPrice) {
        body.price = String(req.limitPrice);
      }
      data = await this.request<{ orderId: string; clientOid?: string }>(
        'POST', '/api/v2/mix/order/place-order', body
      );
    } else {
      // Spot order
      const body: Record<string, unknown> = {
        symbol: req.symbol,
        side: req.side,
        orderType: req.type,
        size: String(truncatedQty),
        force: req.timeInForce || 'gtc',
      };
      if (req.type === 'limit' && req.limitPrice) {
        body.price = String(req.limitPrice);
      }
      data = await this.request<{ orderId: string; clientOid?: string }>(
        'POST', '/api/v2/spot/trade/place-order', body
      );
    }

    return {
      brokerId: data.orderId,
      symbol: req.symbol,
      side: req.side,
      quantity: req.quantity,
      type: req.type,
      status: 'new',
      createdAt: new Date().toISOString(),
      raw: data as unknown as Record<string, unknown>,
    };
  }

  /**
   * Get a specific order by broker ID.
   * GET /api/v2/spot/trade/orderInfo?orderId=X
   */
  async getOrder(brokerId: string): Promise<OrderResponse> {
    const path = this.simulated
      ? `/api/v2/mix/order/detail?orderId=${brokerId}&productType=USDT-FUTURES`
      : `/api/v2/spot/trade/orderInfo?orderId=${brokerId}`;

    const data = await this.request<BitgetOrderInfo[]>('GET', path);

    if (!data || data.length === 0) {
      throw new Error(`Order ${brokerId} not found`);
    }

    return this.toOrderResponse(data[0]);
  }

  /**
   * Cancel a pending order.
   * POST /api/v2/spot/trade/cancel-order
   */
  async cancelOrder(brokerId: string): Promise<CancelResult> {
    try {
      if (this.simulated) {
        // Mix cancel requires symbol — not available here; use REST fallback
        // Callers that know the symbol should use placeOrder with side=sell tradeSide=close
        return { success: false, message: 'Cancel order in futures mode requires symbol — use closePosition instead' };
      }
      await this.request(
        'POST',
        '/api/v2/spot/trade/cancel-order',
        { orderId: brokerId }
      );
      return { success: true, message: 'Order cancelled' };
    } catch (error) {
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Cancel failed',
      };
    }
  }

  /**
   * Get order history (filled/cancelled).
   * GET /api/v2/spot/trade/history-orders
   */
  async getOrderHistory(params?: OrderHistoryParams): Promise<OrderResponse[]> {
    const qs: string[] = [];

    if (this.simulated) {
      qs.push('productType=USDT-FUTURES');
      if (params?.symbol) qs.push(`symbol=${params.symbol}`);
      if (params?.limit) qs.push(`limit=${params.limit}`);
      if (params?.since) qs.push(`startTime=${new Date(params.since).getTime()}`);
      const path = '/api/v2/mix/order/history-orders' + (qs.length ? `?${qs.join('&')}` : '');
      const data = await this.request<BitgetOrderInfo[]>('GET', path);
      return (data || []).map((o) => this.toOrderResponse(o));
    }

    if (params?.symbol) qs.push(`symbol=${params.symbol}`);
    if (params?.limit) qs.push(`limit=${params.limit}`);
    if (params?.since) qs.push(`startTime=${new Date(params.since).getTime()}`);
    const path = '/api/v2/spot/trade/history-orders' + (qs.length ? `?${qs.join('&')}` : '');
    const data = await this.request<BitgetOrderInfo[]>('GET', path);
    return (data || []).map((o) => this.toOrderResponse(o));
  }

  // ── Positions ──────────────────────────────────────────────

  /**
   * Get positions (spot = non-USDT balances with real-time prices).
   *
   * For spot trading, "positions" are wallet balances. We enrich each
   * asset with the current market price from the public ticker endpoint.
   *
   * Note: avgEntryPrice is NOT available from Bitget spot API.
   * The API route layer joins this with our Orders table to compute it.
   */
  async getPositions(): Promise<Position[]> {
    if (this.simulated) {
      // Futures positions
      const rawPositions = await this.request<BitgetMixPosition[]>(
        'GET',
        '/api/v2/mix/position/all-position?productType=USDT-FUTURES'
      );
      return (rawPositions || [])
        .filter((p) => Number(p.total) > 0)
        .map((p) => {
          const qty = Number(p.total);
          const avgEntry = Number(p.openPriceAvg);
          const markPrice = Number(p.markPrice);
          const unrealizedPl = Number(p.unrealizedPL);
          return {
            symbol: p.symbol,
            quantity: qty,
            avgEntryPrice: avgEntry,
            currentPrice: markPrice,
            marketValue: qty * markPrice,
            unrealizedPl,
            unrealizedPlPct: avgEntry > 0 ? (unrealizedPl / (avgEntry * qty)) * 100 : 0,
            side: (p.holdSide === 'short' ? 'short' : 'long') as 'long' | 'short',
          };
        });
    }

    // Spot positions
    const assets = await this.request<BitgetAsset[]>(
      'GET',
      '/api/v2/spot/account/assets'
    );

    const nonUsdtAssets = assets.filter(
      (a) => a.coin !== 'USDT' && Number(a.available) + Number(a.frozen) > 0
    );

    // Fetch current prices in parallel for all held assets
    const positions = await Promise.all(
      nonUsdtAssets.map(async (a) => {
        const symbol = `${a.coin}USDT`;
        const qty = Number(a.available) + Number(a.frozen);
        const currentPrice = await this.getTickerPrice(symbol);
        const marketValue = qty * currentPrice;

        return {
          symbol,
          quantity: qty,
          avgEntryPrice: 0,          // Filled by API route from our Orders table
          currentPrice,
          marketValue,
          unrealizedPl: 0,           // Needs avgEntryPrice to compute
          unrealizedPlPct: 0,
          side: 'long' as const,
        };
      })
    );

    return positions;
  }

  /**
   * Close a position.
   *
   * Spot: sell the full available asset balance.
   * Futures: place a sell-close order for the held size.
   */
  async closePosition(symbol: string, quantity?: number): Promise<OrderResponse> {
    if (this.simulated) {
      // Fetch all futures positions to find the actual available quantity
      const positions = await this.request<BitgetMixPosition[]>(
        'GET',
        '/api/v2/mix/position/all-position?productType=USDT-FUTURES'
      );
      // Accept any holdSide (long, short, net — one-way mode uses "net" or "long")
      const pos = (positions || []).find((p) => p.symbol === symbol);
      if (!pos || Number(pos.available) <= 0) {
        throw new Error(`No available position for ${symbol} to close`);
      }
      const closeQty = quantity
        ? Math.min(quantity, Number(pos.available))
        : Number(pos.available);

      // Build close order based on account mode:
      // - One-way mode: holdSide === 'net' → just side:'sell', no tradeSide/holdSide
      // - Hedge mode:   holdSide === 'long' → side:'sell', tradeSide:'close', holdSide:'long'
      const isHedgeMode = pos.holdSide.toLowerCase() === 'long';
      const closeBody: Record<string, unknown> = {
        symbol,
        productType: 'USDT-FUTURES',
        marginMode: pos.marginMode || 'crossed',
        marginCoin: pos.marginCoin || 'USDT',
        size: String(closeQty),
        side: 'sell',
        orderType: 'market',
        force: 'gtc',
      };
      if (isHedgeMode) {
        closeBody.tradeSide = 'close';
        closeBody.holdSide = 'long';
      }
      const data = await this.request<{ orderId: string }>(
        'POST', '/api/v2/mix/order/place-order', closeBody
      );
      return {
        brokerId: data?.orderId ?? '',
        symbol,
        side: 'sell',
        quantity: closeQty,
        type: 'market',
        status: 'new',
        createdAt: new Date().toISOString(),
        raw: data as unknown as Record<string, unknown>,
      };
    }

    // Spot: sell the full available balance
    if (!quantity) {
      const assets = await this.request<BitgetAsset[]>(
        'GET',
        '/api/v2/spot/account/assets'
      );
      const coin = symbol.replace('USDT', '');
      const asset = assets.find((a) => a.coin === coin);
      if (!asset || Number(asset.available) <= 0) {
        throw new Error(`No available ${coin} balance to close`);
      }
      quantity = Number(asset.available);
    }

    return this.placeOrder({
      symbol,
      side: 'sell',
      quantity,
      type: 'market',
      timeInForce: 'ioc',
    });
  }

  // ── Account ────────────────────────────────────────────────

  /**
   * Get account info.
   * Simulated mode: reads from Futures (mix) account API.
   * Spot mode: sums USDT balance + estimates value of held assets.
   */
  async getAccount(): Promise<AccountInfo> {
    if (this.simulated) {
      const accounts = await this.request<BitgetMixAccount[]>(
        'GET',
        '/api/v2/mix/account/accounts?productType=USDT-FUTURES'
      );
      const usdtAccount = (accounts || []).find((a) => a.marginCoin === 'USDT') ?? accounts?.[0];
      const equity = usdtAccount ? Number((usdtAccount as unknown as Record<string,string>)['equity'] ?? (usdtAccount as unknown as Record<string,string>)['usdtEquity'] ?? 0) : 0;
      const available = usdtAccount ? Number((usdtAccount as unknown as Record<string,string>)['available'] ?? (usdtAccount as unknown as Record<string,string>)['crossedMaxAvailable'] ?? 0) : 0;
      return {
        equity,
        buyingPower: available,
        cash: equity,
        currency: 'USDT',
        raw: { accounts } as unknown as Record<string, unknown>,
      };
    }

    const assets = await this.request<BitgetAsset[]>(
      'GET',
      '/api/v2/spot/account/assets'
    );

    const usdt = assets.find((a) => a.coin === 'USDT');
    const usdtAvailable = usdt ? Number(usdt.available) : 0;
    const usdtFrozen = usdt ? Number(usdt.frozen) : 0;
    const usdtTotal = usdtAvailable + usdtFrozen;

    // Estimate total equity including held assets
    const nonUsdtAssets = assets.filter(
      (a) => a.coin !== 'USDT' && Number(a.available) + Number(a.frozen) > 0
    );

    let assetValue = 0;
    if (nonUsdtAssets.length > 0) {
      const values = await Promise.all(
        nonUsdtAssets.map(async (a) => {
          const qty = Number(a.available) + Number(a.frozen);
          const price = await this.getTickerPrice(`${a.coin}USDT`);
          return qty * price;
        })
      );
      assetValue = values.reduce((sum, v) => sum + v, 0);
    }

    return {
      equity: usdtTotal + assetValue,
      buyingPower: usdtAvailable,
      cash: usdtTotal,
      currency: 'USDT',
      raw: { assets } as unknown as Record<string, unknown>,
    };
  }
}

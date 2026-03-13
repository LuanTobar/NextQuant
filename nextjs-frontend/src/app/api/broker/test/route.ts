import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';

/**
 * POST /api/broker/test — Test a broker connection without saving
 * Makes a test API call to verify credentials are valid.
 */
export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { broker, apiKey, apiSecret, environment, passphrase, simulated } = await req.json();

  if (!broker || !apiKey || !apiSecret) {
    return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
  }

  try {
    if (broker === 'ALPACA') {
      return await testAlpaca(apiKey, apiSecret, environment || 'paper');
    } else if (broker === 'BITGET') {
      return await testBitget(apiKey, apiSecret, passphrase, !!simulated);
    }

    return NextResponse.json({ error: `Unsupported broker: ${broker}` }, { status: 400 });
  } catch (error) {
    console.error('Broker test error:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to connect to broker. Check your credentials and try again.' },
      { status: 500 }
    );
  }
}

async function testAlpaca(apiKey: string, apiSecret: string, env: string) {
  const baseUrl = env === 'live'
    ? 'https://api.alpaca.markets'
    : 'https://paper-api.alpaca.markets';

  const res = await fetch(`${baseUrl}/v2/account`, {
    headers: {
      'APCA-API-KEY-ID': apiKey,
      'APCA-API-SECRET-KEY': apiSecret,
    },
  });

  if (!res.ok) {
    const body = await res.text();
    console.error('Alpaca test failed:', res.status, body);
    const msg = res.status === 401 || res.status === 403
      ? 'Invalid API credentials. Please check your key and secret.'
      : `Alpaca connection failed (HTTP ${res.status}). Please try again.`;
    return NextResponse.json({ success: false, error: msg });
  }

  const account = await res.json();
  return NextResponse.json({
    success: true,
    broker: 'ALPACA',
    environment: env,
    account: {
      id: account.id,
      status: account.status,
      equity: account.equity,
      buying_power: account.buying_power,
      currency: account.currency,
    },
  });
}

async function testBitget(
  apiKey: string,
  apiSecret: string,
  passphrase?: string,
  simulated = false,
) {
  if (!passphrase) {
    return NextResponse.json({
      success: false,
      error: 'Bitget requires a passphrase',
    });
  }

  const { createHmac } = await import('crypto');

  // Bitget signature: timestamp + method + requestPath + body
  const timestamp = Date.now().toString();
  const method = 'GET';
  // Simulated/demo keys use the futures (mix) API; spot keys use the spot API
  const requestPath = simulated
    ? '/api/v2/mix/account/accounts?productType=USDT-FUTURES'
    : '/api/v2/spot/account/assets';
  const signPayload = timestamp + method + requestPath;

  const signature = createHmac('sha256', apiSecret)
    .update(signPayload)
    .digest('base64');

  const res = await fetch(`https://api.bitget.com${requestPath}`, {
    headers: {
      'ACCESS-KEY': apiKey,
      'ACCESS-SIGN': signature,
      'ACCESS-PASSPHRASE': passphrase,
      'ACCESS-TIMESTAMP': timestamp,
      'Content-Type': 'application/json',
      'locale': 'en-US',
    },
  });

  if (!res.ok) {
    const body = await res.text();
    console.error('Bitget test failed:', res.status, body);
    const msg = res.status === 401 || res.status === 403
      ? 'Invalid API credentials. Please check your key, secret, and passphrase.'
      : `Bitget connection failed (HTTP ${res.status}). Please try again.`;
    return NextResponse.json({ success: false, error: msg });
  }

  const data = await res.json();
  if (data.code !== '00000') {
    return NextResponse.json({
      success: false,
      error: `Bitget error: ${data.msg || data.code}`,
    });
  }

  // Extract equity for display
  let equity: number | undefined;
  if (simulated && Array.isArray(data.data)) {
    const usdtAccount = data.data.find((a: { marginCoin: string; equity: string }) => a.marginCoin === 'USDT');
    if (usdtAccount) equity = parseFloat(usdtAccount.equity);
  }

  return NextResponse.json({
    success: true,
    broker: 'BITGET',
    environment: simulated ? 'simulated' : 'spot',
    ...(equity !== undefined ? { account: { equity } } : {}),
    message: 'Connection verified',
  });
}

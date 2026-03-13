import { NextRequest, NextResponse } from 'next/server';
import { getLatestPrices, getLatestSignals } from '@/lib/questdb-client';
import { checkChatLimit } from '@/lib/plan-guard';
import { chatLimiter } from '@/lib/rate-limit';

const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;

export async function POST(req: NextRequest) {
  const { message } = await req.json();

  if (!message) {
    return NextResponse.json({ response: 'Please send a message.' }, { status: 400 });
  }

  // Enforce chat limits per plan
  const planCheck = await checkChatLimit();
  if (!planCheck.allowed) {
    return NextResponse.json(
      { response: planCheck.reason || 'Chat limit reached. Upgrade to Pro for unlimited.' },
      { status: 429 }
    );
  }

  // Rate limit per user (in-memory)
  const ip = req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'unknown';
  const rateCheck = await chatLimiter.check(ip);
  if (!rateCheck.allowed) {
    return NextResponse.json(
      { response: 'You are sending messages too fast. Please wait a moment.' },
      { status: 429 }
    );
  }

  try {
    // Gather real market context from QuestDB
    const [prices, signals] = await Promise.allSettled([
      getLatestPrices(),
      getLatestSignals(),
    ]);

    const priceData = prices.status === 'fulfilled' ? prices.value : [];
    const signalData = signals.status === 'fulfilled' ? signals.value : [];

    const marketContext = buildMarketContext(priceData, signalData);

    // Try Claude API if key is available
    if (ANTHROPIC_API_KEY && ANTHROPIC_API_KEY.startsWith('sk-ant-') && ANTHROPIC_API_KEY.length > 20) {
      try {
        const llmResponse = await callClaude(message, marketContext);
        if (llmResponse) {
          return NextResponse.json({ response: llmResponse });
        }
      } catch (e) {
        console.error('Claude API call failed, falling back to pattern matching:', e);
      }
    }

    // Fallback: pattern-matching with real data
    const response = generateFallbackResponse(message, priceData, signalData);
    return NextResponse.json({ response });
  } catch {
    return NextResponse.json(
      { response: 'Sorry, I encountered an error processing your request.' },
      { status: 500 }
    );
  }
}

function buildMarketContext(
  prices: Array<{ symbol: string; close: number; volume: number; timestamp: string }>,
  signals: Array<{
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
  }>
): string {
  let ctx = '';

  if (prices.length > 0) {
    ctx += 'CURRENT MARKET PRICES:\n';
    for (const p of prices) {
      const exch = (p as Record<string, unknown>).exchange || 'US';
      ctx += `  ${p.symbol} [${exch}]: $${p.close.toFixed(2)} (vol: ${p.volume}, at ${p.timestamp})\n`;
    }
  }

  if (signals.length > 0) {
    ctx += '\nML SIGNALS (from our causal analysis pipeline):\n';
    for (const s of signals) {
      const exch = (s as Record<string, unknown>).exchange || 'US';
      const expectedReturn = ((s.predicted_close - s.current_price) / s.current_price * 100).toFixed(2);
      ctx += `  ${s.symbol} [${exch}]: Signal=${s.signal}, Price=$${s.current_price.toFixed(2)}, `;
      ctx += `Predicted=$${s.predicted_close.toFixed(2)} (${expectedReturn}%), `;
      ctx += `Regime=${s.regime}, Volatility=${(s.volatility * 100).toFixed(1)}%, `;
      ctx += `Causal: ${s.causal_description}\n`;
    }
  }

  return ctx || 'No market data available yet. The system is warming up.';
}

async function callClaude(userMessage: string, marketContext: string): Promise<string | null> {
  const systemPrompt = `You are the NexQuant Causal Copilot — an AI investment assistant powered by causal inference, regime detection, and predictive models.

You have access to REAL-TIME market data and ML signals from the NexQuant platform. Use the data below to give accurate, data-driven responses.

${marketContext}

GUIDELINES:
- Always reference actual numbers from the data above (prices, signals, predictions)
- Explain signals using causal reasoning ("our causal analyzer detected..." rather than "the market...")
- Be concise but insightful — 2-4 sentences for simple questions, more for analysis
- When discussing risk, reference the volatility regime and actual volatility numbers
- Never fabricate data — if you don't have data for a symbol, say so
- NexQuant tracks multiple exchanges: CRYPTO (24/7), US (NYSE/NASDAQ), LSE (London), BME (Madrid), TSE (Tokyo)
- CRYPTO symbols: BINANCE:BTCUSDT, BINANCE:ETHUSDT, BINANCE:SOLUSDT, BINANCE:XRPUSDT, BINANCE:ADAUSDT (always live, 24/7)
- US symbols: AAPL, GOOGL, MSFT, AMZN, TSLA
- LSE symbols: VOD.L, BP.L, HSBA.L, AZN.L, SHEL.L
- BME symbols: SAN.MC, TEF.MC, IBE.MC, ITX.MC, BBVA.MC
- TSE symbols: 7203.T, 6758.T, 9984.T, 8306.T, 6861.T
- Each symbol has an [exchange] tag in the data — use it to identify which market
- Respond in the same language the user writes in (Spanish, English, etc.)`;

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': ANTHROPIC_API_KEY!,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 500,
      system: systemPrompt,
      messages: [
        { role: 'user', content: userMessage },
      ],
    }),
  });

  if (!response.ok) {
    const errBody = await response.text();
    console.error('Claude API error:', response.status, errBody);
    return null;
  }

  const data = await response.json();
  // Anthropic Messages API returns content as array of blocks
  const textBlock = data.content?.find((block: { type: string; text?: string }) => block.type === 'text');
  return textBlock?.text || null;
}

function generateFallbackResponse(
  message: string,
  prices: Array<{ symbol: string; close: number; volume: number; timestamp: string }>,
  signals: Array<{
    symbol: string;
    signal: string;
    current_price: number;
    predicted_close: number;
    regime: string;
    causal_effect: number;
    causal_description: string;
    volatility: number;
    confidence_low: number;
    confidence_high: number;
  }>
): string {
  const lower = message.toLowerCase();
  const symbolMatch = message.toUpperCase().match(/\b(AAPL|GOOGL|MSFT|AMZN|TSLA)\b/);
  const symbol = symbolMatch ? symbolMatch[1] : null;

  // Find real data for mentioned symbol
  const price = prices.find((p) => p.symbol === symbol);
  const sig = signals.find((s) => s.symbol === symbol);

  const priceStr = price ? `$${price.close.toFixed(2)}` : 'N/A';

  if ((lower.includes('why') && lower.includes('drop')) || (lower.includes('why') && lower.includes('down'))) {
    if (sig) {
      return `Based on our causal analysis of ${symbol} (currently at ${priceStr}), the causal analyzer found: "${sig.causal_description}" with a causal effect of ${sig.causal_effect.toFixed(2)}. The current regime is ${sig.regime} with ${(sig.volatility * 100).toFixed(1)}% annualized volatility. Signal: ${sig.signal}.`;
    }
    return symbol
      ? `I can see ${symbol} at ${priceStr} but don't have enough signal data yet. The ML pipeline needs a few more snapshots to generate causal insights.`
      : 'Which stock are you asking about? I track AAPL, GOOGL, MSFT, AMZN, and TSLA.';
  }

  if (lower.includes('predict') || lower.includes('outlook') || lower.includes('forecast')) {
    if (sig) {
      const expReturn = ((sig.predicted_close - sig.current_price) / sig.current_price * 100).toFixed(2);
      return `Our predictive model for ${symbol}: current price ${priceStr}, predicted close $${sig.predicted_close.toFixed(2)} (${Number(expReturn) >= 0 ? '+' : ''}${expReturn}%). Confidence range: $${sig.confidence_low.toFixed(2)} - $${sig.confidence_high.toFixed(2)}. Regime: ${sig.regime}. Signal: ${sig.signal}.`;
    }
    return symbol
      ? `${symbol} is currently at ${priceStr}. Prediction data is still being computed — please wait for the ML pipeline to generate enough snapshots.`
      : 'Which ticker would you like a prediction for? I track AAPL, GOOGL, MSFT, AMZN, and TSLA.';
  }

  if (lower.includes('regime') || lower.includes('volatility') || lower.includes('market condition')) {
    if (signals.length > 0) {
      const regimes = signals.map((s) => `${s.symbol}: ${s.regime} (vol ${(s.volatility * 100).toFixed(1)}%)`);
      return `Current market regime across tracked symbols:\n${regimes.join('\n')}\n\nThis classification is updated every 5 seconds from our regime detection model.`;
    }
    return 'Regime data is still being computed. The ML pipeline needs a few more snapshots.';
  }

  if (lower.includes('signal') || lower.includes('buy') || lower.includes('sell') || lower.includes('should i')) {
    if (sig) {
      return `Composite ML signal for ${symbol}: ${sig.signal}. Price: ${priceStr}, predicted: $${sig.predicted_close.toFixed(2)}. Causal insight: "${sig.causal_description}". Regime: ${sig.regime} (${(sig.volatility * 100).toFixed(1)}% vol).`;
    }
    if (signals.length > 0) {
      const allSignals = signals.map((s) => `${s.symbol}: ${s.signal} ($${s.current_price.toFixed(2)})`);
      return `Current ML signals:\n${allSignals.join('\n')}\n\nAsk about a specific symbol for detailed causal analysis.`;
    }
    return 'Signal data is still being generated. Please wait a moment.';
  }

  // Default: show summary of available data
  if (signals.length > 0) {
    const summary = signals.map((s) => `${s.symbol}: ${s.signal} at $${s.current_price.toFixed(2)}`).join(', ');
    return `I'm the NexQuant Causal Copilot. Current signals: ${summary}. Ask me about predictions, market regime, causal analysis, or specific stocks!`;
  }

  return `I'm the NexQuant Causal Copilot. I can analyze AAPL, GOOGL, MSFT, AMZN, and TSLA using causal inference. Try asking:\n- "What's the prediction for AAPL?"\n- "What's the current market regime?"\n- "Should I buy TSLA?"\n- "Why did MSFT drop?"`;
}

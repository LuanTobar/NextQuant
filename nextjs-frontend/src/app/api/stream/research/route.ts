/**
 * SSE endpoint: streams ml.research.brief messages from NATS to the browser.
 * No auth required — research briefs are market-level, not user-level.
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

import { getNatsConnection, sc } from '@/lib/nats-server';

export async function GET(request: Request) {
  let sub: Awaited<ReturnType<Awaited<ReturnType<typeof getNatsConnection>>['subscribe']>> | null = null;

  const stream = new ReadableStream({
    async start(controller) {
      const enc = new TextEncoder();

      const send = (data: string) => {
        try {
          controller.enqueue(enc.encode(`data: ${data}\n\n`));
        } catch {
          // client disconnected
        }
      };

      // Keep-alive comment every 15 s
      const keepAlive = setInterval(() => {
        try {
          controller.enqueue(enc.encode(': keep-alive\n\n'));
        } catch {
          clearInterval(keepAlive);
        }
      }, 15_000);

      try {
        const nc = await getNatsConnection();
        sub = nc.subscribe('ml.research.brief');

        // Forward messages
        (async () => {
          for await (const msg of sub!) {
            send(sc.decode(msg.data));
          }
        })();

        // Cleanup on client disconnect
        request.signal.addEventListener('abort', () => {
          clearInterval(keepAlive);
          sub?.unsubscribe();
          try { controller.close(); } catch { /* already closed */ }
        });
      } catch (err) {
        clearInterval(keepAlive);
        send(JSON.stringify({ error: 'NATS unavailable' }));
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

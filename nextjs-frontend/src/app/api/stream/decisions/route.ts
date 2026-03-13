/**
 * SSE endpoint: streams agent.decisions.{userId} messages from NATS.
 * Auth-gated — only delivers decisions belonging to the authenticated user.
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { getNatsConnection, sc } from '@/lib/nats-server';

export async function GET(request: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return new Response('Unauthorized', { status: 401 });
  }

  const userId = session.user.id;

  const stream = new ReadableStream({
    async start(controller) {
      const enc = new TextEncoder();

      const send = (data: string) => {
        try {
          controller.enqueue(enc.encode(`data: ${data}\n\n`));
        } catch { /* disconnected */ }
      };

      const keepAlive = setInterval(() => {
        try {
          controller.enqueue(enc.encode(': keep-alive\n\n'));
        } catch {
          clearInterval(keepAlive);
        }
      }, 15_000);

      try {
        const nc = await getNatsConnection();
        const sub = nc.subscribe(`agent.decisions.${userId}`);

        (async () => {
          for await (const msg of sub) {
            send(sc.decode(msg.data));
          }
        })();

        request.signal.addEventListener('abort', () => {
          clearInterval(keepAlive);
          sub.unsubscribe();
          try { controller.close(); } catch { /* already closed */ }
        });
      } catch {
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

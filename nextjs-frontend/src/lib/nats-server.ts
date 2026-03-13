/**
 * Server-side NATS singleton for use in Next.js API routes (Node.js runtime only).
 * Lazy-connects on first call and reuses the connection across requests.
 */
import { connect, NatsConnection, StringCodec } from 'nats';

let _conn: NatsConnection | null = null;
let _connecting: Promise<NatsConnection> | null = null;

export const sc = StringCodec();

export async function getNatsConnection(): Promise<NatsConnection> {
  if (_conn && !_conn.isClosed()) return _conn;

  if (_connecting) return _connecting;

  const url = process.env.NATS_URL ?? 'nats://localhost:4222';

  _connecting = connect({ servers: url, reconnect: true, maxReconnectAttempts: -1 })
    .then((nc) => {
      _conn = nc;
      _connecting = null;
      // Clean up reference when connection closes
      nc.closed().then(() => { _conn = null; });
      return nc;
    })
    .catch((err) => {
      _connecting = null;
      throw err;
    });

  return _connecting;
}

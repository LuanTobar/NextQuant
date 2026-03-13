/**
 * Broker client factory.
 *
 * Takes a BrokerConnection record (with encrypted keys) and returns
 * the appropriate BrokerClient implementation with decrypted credentials.
 */

import type { BrokerConnection } from '@prisma/client';
import type { BrokerClient } from './types';
import { AlpacaClient } from './alpaca';
import { BitgetClient } from './bitget';
import { decrypt } from '../encryption';

/**
 * Create a broker client from a database BrokerConnection record.
 *
 * Flow:
 *   1. Decrypt encryptedKey and encryptedSecret from DB
 *   2. Parse encryptedExtra (JSON with environment, passphrase, etc.)
 *   3. Instantiate the correct client class
 */
export function createBrokerClient(connection: BrokerConnection): BrokerClient {
  const apiKey = decrypt(connection.encryptedKey);
  const apiSecret = decrypt(connection.encryptedSecret);
  const extra = connection.encryptedExtra
    ? JSON.parse(decrypt(connection.encryptedExtra))
    : {};

  switch (connection.broker) {
    case 'ALPACA':
      return new AlpacaClient({
        apiKey,
        apiSecret,
        environment: extra.environment || 'paper',
      });

    case 'BITGET':
      return new BitgetClient({
        apiKey,
        apiSecret,
        passphrase: extra.passphrase || '',
        simulated: extra.simulated === true,
      });

    default:
      throw new Error(`Unsupported broker: ${connection.broker}`);
  }
}

export type {
  BrokerClient,
  OrderRequest,
  OrderResponse,
  OrderHistoryParams,
  CancelResult,
  AccountInfo,
  Position,
} from './types';

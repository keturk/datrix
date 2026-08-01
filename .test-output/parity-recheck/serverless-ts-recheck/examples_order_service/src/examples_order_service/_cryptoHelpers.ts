/**
 * Crypto helper functions for generated TypeScript code.
 */
import { createHmac, createSign } from 'crypto';

export async function _cryptoSign(
  keyId: string,
  message: string,
  signingAlgorithm: string,
): Promise<string> {
  const key = process.env[`CRYPTO_KEY_${keyId}`] ?? process.env.CRYPTO_SIGNING_KEY;
  if (!key) throw new Error(`Signing key '${keyId}' is not configured`);
  const normalized = signingAlgorithm.toLowerCase();
  if (normalized.includes('hmac') || normalized.includes('sha256')) {
    return createHmac('sha256', key).update(message).digest('base64url');
  }
  const signer = createSign(signingAlgorithm);
  signer.update(message);
  signer.end();
  return signer.sign(key, 'base64url');
}

/**
 * Push notification helper functions for generated TypeScript code.
 *
 * Provider: fcm
 *
 * Exports _pushSend, _pushSendBulk, and _pushGetStatus with unified
 * signatures regardless of the configured push provider.
 */
import * as admin from 'firebase-admin';

let _firebaseApp: admin.app.App | null = null;

function _getFirebaseApp(): admin.app.App {
  if (_firebaseApp) return _firebaseApp;
  if (!admin.apps.length) {
    admin.initializeApp({
      credential: admin.credential.applicationDefault(),
    });
  }
  _firebaseApp = admin.app();
  return _firebaseApp;
}

export async function _pushSend(
  payload: Record<string, unknown>,
): Promise<string> {
  const token = payload.userId as string | undefined;
  if (!token) {
    throw new Error('Push payload must include userId (device token)');
  }
  const result = await admin.messaging(_getFirebaseApp()).send({
    token,
    notification: {
      title: (payload.title as string) ?? '',
      body: (payload.template as string) ?? '',
    },
    data: (payload.data as Record<string, string>) ?? {},
  });
  return result;
}

export async function _pushSendBulk(
  tokens: string[],
  payload: Record<string, unknown>,
): Promise<string[]> {
  const messaging = admin.messaging(_getFirebaseApp());
  const messages: admin.messaging.Message[] = tokens.map((token) => ({
    token,
    notification: {
      title: (payload.title as string) ?? '',
      body: (payload.template as string) ?? '',
    },
    data: (payload.data as Record<string, string>) ?? {},
  }));
  const response = await messaging.sendEach(messages);
  return response.responses.map((r) => r.messageId ?? '');
}

export async function _pushGetStatus(
  messageId: string,
): Promise<Record<string, string>> {
  // FCM does not expose per-message delivery status via a polling API.
  // Delivery receipts require Firebase Cloud Messaging Data API.
  return { messageId, status: 'SENT' };
}

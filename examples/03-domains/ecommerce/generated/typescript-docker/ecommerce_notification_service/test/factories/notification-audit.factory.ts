import { NotificationAudit } from '../../src/entities/notification-audit.entity';

/**
 * Build a partial NotificationAudit with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildNotificationAudit(
  overrides?: Partial<NotificationAudit>,
): Partial<NotificationAudit> {
  return {
    orderId: crypto.randomUUID(),
    recipientEmail: 'user@example.com',
    orderNumber: `x`,
    ...overrides,
  };
}

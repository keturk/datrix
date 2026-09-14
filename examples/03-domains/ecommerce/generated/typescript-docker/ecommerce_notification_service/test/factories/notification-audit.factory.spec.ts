import { buildNotificationAudit } from './notification-audit.factory';

describe('buildNotificationAudit', () => {
  it('should return a valid partial entity', () => {
    const result = buildNotificationAudit();
    expect(result).toBeDefined();
    expect(result.orderId).toBeDefined();
    expect(result.recipientEmail).toBeDefined();
    expect(result.orderNumber).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      orderId: crypto.randomUUID(),
    };
    const result = buildNotificationAudit(overrides);
    expect(result.orderId).toBe(overrides.orderId);
  });

  it('should produce different instances', () => {
    const a = buildNotificationAudit();
    const b = buildNotificationAudit();
    expect(a).not.toBe(b);
  });
});

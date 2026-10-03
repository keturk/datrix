import { UserSession } from '../../src/entities/user-session.entity';

/**
 * Build a partial UserSession with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildUserSession(
  overrides?: Partial<UserSession>,
): Partial<UserSession> {
  return {
    token: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    deviceName: 'test',
    ipAddress: '192.168.1.1',
    userAgent: 'test',
    expiresAt: new Date('2025-01-15T12:00:00Z'),
    lastActivityAt: new Date('2025-01-15T12:00:00Z'),
    user: crypto.randomUUID(),
    ...overrides,
  };
}

import { UserSession } from '../../src/entities/user-session.entity';

/**
 * Build a partial UserSession with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildUserSession(
  overrides?: Partial<UserSession>,
): Partial<UserSession> {
  return {
    token: `x`,
    deviceName: `x`,
    ipAddress: '192.168.1.1',
    userAgent: `x`,
    expiresAt: new Date(),
    lastActivityAt: new Date(),
    userId: crypto.randomUUID(),
    ...overrides,
  };
}

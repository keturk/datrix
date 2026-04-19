import { UserPreferences } from '../../src/entities/user-preferences.entity';

/**
 * Build a partial UserPreferences with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildUserPreferences(
  overrides?: Partial<UserPreferences>,
): Partial<UserPreferences> {
  return {
    language: `x`,
    timezone: `x`,
    emailNotifications: true,
    smsNotifications: true,
    preferences: {},
    userId: crypto.randomUUID(),
    ...overrides,
  };
}

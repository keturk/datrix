import { buildUserPreferences } from './user-preferences.factory';

describe('buildUserPreferences', () => {
  it('should return a valid partial entity', () => {
    const result = buildUserPreferences();
    expect(result).toBeDefined();
    expect(result.language).toBeDefined();
    expect(result.timezone).toBeDefined();
    expect(result.emailNotifications).toBeDefined();
    expect(result.smsNotifications).toBeDefined();
    expect(result.preferences).toBeDefined();
    expect(result.userId).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      language: `x`,
    };
    const result = buildUserPreferences(overrides);
    expect(result.language).toBe(overrides.language);
  });

  it('should produce different instances', () => {
    const a = buildUserPreferences();
    const b = buildUserPreferences();
    expect(a).not.toBe(b);
  });
});

import { buildUserPreferences } from './user-preferences.factory';

describe('buildUserPreferences', () => {
  it('should return a valid partial entity', () => {
    const result = buildUserPreferences();
    expect(result).toBeDefined();
    expect(result.preferences).toBeDefined();
    expect(result.user).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      preferences: { key: 'value' },
    };
    const result = buildUserPreferences(overrides);
    expect(result.preferences).toBe(overrides.preferences);
  });

  it('should produce different instances', () => {
    const a = buildUserPreferences();
    const b = buildUserPreferences();
    expect(a).not.toBe(b);
  });
});

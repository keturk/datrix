import { UserPreferences } from '../src/entities/user-preferences.entity';

describe('UserPreferences Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new UserPreferences();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new UserPreferences();
    const languageVal = 'test-value';
    const timezoneVal = 'test-value';
    const emailNotificationsVal = true;
    const smsNotificationsVal = true;
    const preferencesVal = { key: 'value' };
    const userIdVal = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
    entity.language = languageVal;
    entity.timezone = timezoneVal;
    entity.emailNotifications = emailNotificationsVal;
    entity.smsNotifications = smsNotificationsVal;
    entity.preferences = preferencesVal;
    entity.userId = userIdVal;
    expect(entity.language).toBe(languageVal);
    expect(entity.timezone).toBe(timezoneVal);
    expect(entity.emailNotifications).toBe(emailNotificationsVal);
    expect(entity.smsNotifications).toBe(smsNotificationsVal);
    expect(entity.preferences).toBe(preferencesVal);
    expect(entity.userId).toBe(userIdVal);
  });

  it('should update field values', () => {
    const entity = new UserPreferences();
    const languageVal = 'updated-value';
    const timezoneVal = 'updated-value';
    const emailNotificationsVal = false;
    const smsNotificationsVal = false;
    const preferencesVal = { key: 'updated' };
    const userIdVal = 'b1ffbc99-9c0b-4ef8-bb6d-6bb9bd380a22';
    entity.language = languageVal;
    entity.timezone = timezoneVal;
    entity.emailNotifications = emailNotificationsVal;
    entity.smsNotifications = smsNotificationsVal;
    entity.preferences = preferencesVal;
    entity.userId = userIdVal;
    expect(entity.language).toBe(languageVal);
    expect(entity.timezone).toBe(timezoneVal);
    expect(entity.emailNotifications).toBe(emailNotificationsVal);
    expect(entity.smsNotifications).toBe(smsNotificationsVal);
    expect(entity.preferences).toBe(preferencesVal);
    expect(entity.userId).toBe(userIdVal);
  });

  it('should have server-managed fields', () => {
    const entity = new UserPreferences();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});

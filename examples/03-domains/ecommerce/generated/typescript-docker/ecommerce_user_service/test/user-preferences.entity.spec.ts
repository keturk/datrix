import { UserPreferences } from '../src/ecommerce_user_service/entities/user_db/user-preferences.entity';

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
    const userIdVal = '550e8400-e29b-41d4-a716-446655440000';
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
    const userIdVal = '660e8400-e29b-41d4-a716-446655440001';
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
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
    expect(entity.id).toBeUndefined();
  });
});

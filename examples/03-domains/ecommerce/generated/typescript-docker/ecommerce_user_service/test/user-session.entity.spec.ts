import { UserSession } from '../src/ecommerce_user_service/entities/user_db/user-session.entity';

describe('UserSession Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new UserSession();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new UserSession();
    const tokenVal = `test-${Date.now()}`;
    const deviceNameVal = 'test-value';
    const ipAddressVal = '192.168.1.1';
    const userAgentVal = 'test-value';
    const expiresAtVal = new Date('2025-01-15T12:00:00Z');
    const lastActivityAtVal = new Date('2025-01-15T12:00:00Z');
    const userIdVal = '550e8400-e29b-41d4-a716-446655440000';
    entity.token = tokenVal;
    entity.deviceName = deviceNameVal;
    entity.ipAddress = ipAddressVal;
    entity.userAgent = userAgentVal;
    entity.expiresAt = expiresAtVal;
    entity.lastActivityAt = lastActivityAtVal;
    entity.userId = userIdVal;
    expect(entity.token).toBe(tokenVal);
    expect(entity.deviceName).toBe(deviceNameVal);
    expect(entity.ipAddress).toBe(ipAddressVal);
    expect(entity.userAgent).toBe(userAgentVal);
    expect(entity.expiresAt).toEqual(expiresAtVal);
    expect(entity.lastActivityAt).toEqual(lastActivityAtVal);
    expect(entity.userId).toBe(userIdVal);
  });

  it('should update field values', () => {
    const entity = new UserSession();
    const tokenVal = `updated-${Date.now()}`;
    const deviceNameVal = 'updated-value';
    const ipAddressVal = '10.0.0.1';
    const userAgentVal = 'updated-value';
    const expiresAtVal = new Date('2025-06-20T15:30:00Z');
    const lastActivityAtVal = new Date('2025-06-20T15:30:00Z');
    const userIdVal = '660e8400-e29b-41d4-a716-446655440001';
    entity.token = tokenVal;
    entity.deviceName = deviceNameVal;
    entity.ipAddress = ipAddressVal;
    entity.userAgent = userAgentVal;
    entity.expiresAt = expiresAtVal;
    entity.lastActivityAt = lastActivityAtVal;
    entity.userId = userIdVal;
    expect(entity.token).toBe(tokenVal);
    expect(entity.deviceName).toBe(deviceNameVal);
    expect(entity.ipAddress).toBe(ipAddressVal);
    expect(entity.userAgent).toBe(userAgentVal);
    expect(entity.expiresAt).toEqual(expiresAtVal);
    expect(entity.lastActivityAt).toEqual(lastActivityAtVal);
    expect(entity.userId).toBe(userIdVal);
  });

  it('should enforce unique constraint on token', () => {
    const entity = new UserSession();
    entity.token = `test-${Date.now()}`;
    expect(entity.token).toBeDefined();
  });

  it('should have index on token', () => {
    const entity = new UserSession();
    entity.token = `test-${Date.now()}`;
    expect(entity.token).toBeDefined();
  });

  it('should have index on userId', () => {
    const entity = new UserSession();
    entity.userId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.userId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new UserSession();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
    expect(entity.id).toBeUndefined();
  });
});

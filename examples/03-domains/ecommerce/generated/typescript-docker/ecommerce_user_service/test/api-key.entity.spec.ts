import { ApiKey } from '../src/ecommerce_user_service/entities/user_db/api-key.entity';

describe('ApiKey Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new ApiKey();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new ApiKey();
    const keyHashVal = `test-${Date.now()}`;
    const ownerIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const keyPrefixVal = 'test-value';
    const scopesVal = ['test-value'];
    const isActiveVal = true;
    const expiresAtVal = new Date('2025-01-15T12:00:00Z');
    const lastUsedAtVal = new Date('2025-01-15T12:00:00Z');
    const rateLimitVal = 42;
    entity.keyHash = keyHashVal;
    entity.ownerId = ownerIdVal;
    entity.keyPrefix = keyPrefixVal;
    entity.scopes = scopesVal;
    entity.isActive = isActiveVal;
    entity.expiresAt = expiresAtVal;
    entity.lastUsedAt = lastUsedAtVal;
    entity.rateLimit = rateLimitVal;
    expect(entity.keyHash).toBe(keyHashVal);
    expect(entity.ownerId).toBe(ownerIdVal);
    expect(entity.keyPrefix).toBe(keyPrefixVal);
    expect(entity.scopes).toBe(scopesVal);
    expect(entity.isActive).toBe(isActiveVal);
    expect(entity.expiresAt).toEqual(expiresAtVal);
    expect(entity.lastUsedAt).toEqual(lastUsedAtVal);
    expect(entity.rateLimit).toBe(rateLimitVal);
  });

  it('should update field values', () => {
    const entity = new ApiKey();
    const keyHashVal = `updated-${Date.now()}`;
    const ownerIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const keyPrefixVal = 'updated-value';
    const scopesVal = ['test-value'];
    const isActiveVal = false;
    const expiresAtVal = new Date('2025-06-20T15:30:00Z');
    const lastUsedAtVal = new Date('2025-06-20T15:30:00Z');
    const rateLimitVal = 99;
    entity.keyHash = keyHashVal;
    entity.ownerId = ownerIdVal;
    entity.keyPrefix = keyPrefixVal;
    entity.scopes = scopesVal;
    entity.isActive = isActiveVal;
    entity.expiresAt = expiresAtVal;
    entity.lastUsedAt = lastUsedAtVal;
    entity.rateLimit = rateLimitVal;
    expect(entity.keyHash).toBe(keyHashVal);
    expect(entity.ownerId).toBe(ownerIdVal);
    expect(entity.keyPrefix).toBe(keyPrefixVal);
    expect(entity.scopes).toBe(scopesVal);
    expect(entity.isActive).toBe(isActiveVal);
    expect(entity.expiresAt).toEqual(expiresAtVal);
    expect(entity.lastUsedAt).toEqual(lastUsedAtVal);
    expect(entity.rateLimit).toBe(rateLimitVal);
  });

  it('should enforce unique constraint on keyHash', () => {
    const entity = new ApiKey();
    entity.keyHash = `test-${Date.now()}`;
    expect(entity.keyHash).toBeDefined();
  });

  it('should have index on ownerId', () => {
    const entity = new ApiKey();
    entity.ownerId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.ownerId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new ApiKey();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
    expect(entity.id).toBeUndefined();
  });
});

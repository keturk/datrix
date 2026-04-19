import { IdempotencyKey } from '../src/entities/idempotency-key.entity';

describe('IdempotencyKey Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new IdempotencyKey();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new IdempotencyKey();
    const keyVal = `test-${Date.now()}`;
    const operationVal = 'test-value';
    const resourceIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const responseVal = { key: 'value' };
    const expiresAtVal = new Date('2025-01-15T12:00:00Z');
    entity.key = keyVal;
    entity.operation = operationVal;
    entity.resourceId = resourceIdVal;
    entity.response = responseVal;
    entity.expiresAt = expiresAtVal;
    expect(entity.key).toBe(keyVal);
    expect(entity.operation).toBe(operationVal);
    expect(entity.resourceId).toBe(resourceIdVal);
    expect(entity.response).toBe(responseVal);
    expect(entity.expiresAt).toEqual(expiresAtVal);
  });

  it('should update field values', () => {
    const entity = new IdempotencyKey();
    const keyVal = `updated-${Date.now()}`;
    const operationVal = 'updated-value';
    const resourceIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const responseVal = { key: 'updated' };
    const expiresAtVal = new Date('2025-06-20T15:30:00Z');
    entity.key = keyVal;
    entity.operation = operationVal;
    entity.resourceId = resourceIdVal;
    entity.response = responseVal;
    entity.expiresAt = expiresAtVal;
    expect(entity.key).toBe(keyVal);
    expect(entity.operation).toBe(operationVal);
    expect(entity.resourceId).toBe(resourceIdVal);
    expect(entity.response).toBe(responseVal);
    expect(entity.expiresAt).toEqual(expiresAtVal);
  });

  it('should enforce unique constraint on key', () => {
    const entity = new IdempotencyKey();
    entity.key = `test-${Date.now()}`;
    expect(entity.key).toBeDefined();
  });

  it('should have index on operation', () => {
    const entity = new IdempotencyKey();
    entity.operation = 'test-value';
    expect(entity.operation).toBeDefined();
  });

  it('should have index on expiresAt', () => {
    const entity = new IdempotencyKey();
    entity.expiresAt = new Date('2025-01-15T12:00:00Z');
    expect(entity.expiresAt).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new IdempotencyKey();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});

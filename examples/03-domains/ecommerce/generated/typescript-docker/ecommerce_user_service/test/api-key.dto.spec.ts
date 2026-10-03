import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateApiKeyDto } from '../src/dto/create-api-key.dto';

describe('CreateApiKeyDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      keyHash: `test-${Date.now()}`,
      ownerId: '550e8400-e29b-41d4-a716-446655440000',
      keyPrefix: 'test-value',
      scopes: ['test-value'],
      isActive: true,
      expiresAt: new Date('2025-01-15T12:00:00Z'),
      lastUsedAt: new Date('2025-01-15T12:00:00Z'),
      rateLimit: 42,
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateApiKeyDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when keyHash is missing', async () => {
    const payload = buildValidPayload();
    delete payload.keyHash;
    const dto = plainToInstance(CreateApiKeyDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'keyHash');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when ownerId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.ownerId;
    const dto = plainToInstance(CreateApiKeyDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'ownerId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when keyPrefix is missing', async () => {
    const payload = buildValidPayload();
    delete payload.keyPrefix;
    const dto = plainToInstance(CreateApiKeyDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'keyPrefix');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when scopes is missing', async () => {
    const payload = buildValidPayload();
    delete payload.scopes;
    const dto = plainToInstance(CreateApiKeyDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'scopes');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when keyHash exceeds max length 64', async () => {
    const payload = buildValidPayload();
    payload.keyHash = 'x'.repeat(64 + 1);
    const dto = plainToInstance(CreateApiKeyDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'keyHash');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when keyPrefix exceeds max length 12', async () => {
    const payload = buildValidPayload();
    payload.keyPrefix = 'x'.repeat(12 + 1);
    const dto = plainToInstance(CreateApiKeyDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'keyPrefix');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateIdempotencyKeyDto } from '../src/dto/create-idempotency-key.dto';

describe('CreateIdempotencyKeyDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      key: `test-${Date.now()}`,
      operation: 'test-value',
      resourceId: '550e8400-e29b-41d4-a716-446655440000',
      response: { key: 'value' },
      expiresAt: new Date('2025-01-15T12:00:00Z'),
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateIdempotencyKeyDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when key is missing', async () => {
    const payload = buildValidPayload();
    delete payload.key;
    const dto = plainToInstance(CreateIdempotencyKeyDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'key');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when operation is missing', async () => {
    const payload = buildValidPayload();
    delete payload.operation;
    const dto = plainToInstance(CreateIdempotencyKeyDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'operation');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when expiresAt is missing', async () => {
    const payload = buildValidPayload();
    delete payload.expiresAt;
    const dto = plainToInstance(CreateIdempotencyKeyDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'expiresAt');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when key exceeds max length 100', async () => {
    const payload = buildValidPayload();
    payload.key = 'x'.repeat(100 + 1);
    const dto = plainToInstance(CreateIdempotencyKeyDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'key');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when operation exceeds max length 50', async () => {
    const payload = buildValidPayload();
    payload.operation = 'x'.repeat(50 + 1);
    const dto = plainToInstance(CreateIdempotencyKeyDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'operation');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { IssueApiKeyRequest } from '../src/dto/issue-api-key-request.struct';

describe('IssueApiKeyRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      scopes: ['test-value'],
      expiresAt: new Date('2025-01-15T12:00:00Z'),
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(IssueApiKeyRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.scopes).toBeDefined();
    expect(instance.expiresAt).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(IssueApiKeyRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when scopes is missing', async () => {
    const payload = buildValidPayload();
    delete payload.scopes;
    const instance = plainToInstance(IssueApiKeyRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});

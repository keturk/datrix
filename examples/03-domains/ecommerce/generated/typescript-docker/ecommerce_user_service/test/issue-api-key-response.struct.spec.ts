import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { IssueApiKeyResponse } from '../src/dto/issue-api-key-response.struct';

describe('IssueApiKeyResponse Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      id: '550e8400-e29b-41d4-a716-446655440000',
      apiKey: 'test-value',
      keyPrefix: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(IssueApiKeyResponse, payload);
    expect(instance).toBeDefined();
    expect(instance.id).toBeDefined();
    expect(instance.apiKey).toBeDefined();
    expect(instance.keyPrefix).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(IssueApiKeyResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when id is missing', async () => {
    const payload = buildValidPayload();
    delete payload.id;
    const instance = plainToInstance(IssueApiKeyResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when apiKey is missing', async () => {
    const payload = buildValidPayload();
    delete payload.apiKey;
    const instance = plainToInstance(IssueApiKeyResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when keyPrefix is missing', async () => {
    const payload = buildValidPayload();
    delete payload.keyPrefix;
    const instance = plainToInstance(IssueApiKeyResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});

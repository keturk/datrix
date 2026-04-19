import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { FedExWebhookRequest } from '../src/dto/fed-ex-webhook-request.struct';

describe('FedExWebhookRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      payload: { key: 'value' },
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(FedExWebhookRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.payload).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(FedExWebhookRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when payload is missing', async () => {
    const payload = buildValidPayload();
    delete payload.payload;
    const instance = plainToInstance(FedExWebhookRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});

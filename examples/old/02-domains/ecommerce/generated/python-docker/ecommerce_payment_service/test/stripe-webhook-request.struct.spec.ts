import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { StripeWebhookRequest } from '../src/dto/stripe-webhook-request.struct';

describe('StripeWebhookRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      payload: { key: 'value' },
      stripeSignature: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(StripeWebhookRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.payload).toBeDefined();
    expect(instance.stripeSignature).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(StripeWebhookRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when payload is missing', async () => {
    const payload = buildValidPayload();
    delete payload.payload;
    const instance = plainToInstance(StripeWebhookRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when stripeSignature is missing', async () => {
    const payload = buildValidPayload();
    delete payload.stripeSignature;
    const instance = plainToInstance(StripeWebhookRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});

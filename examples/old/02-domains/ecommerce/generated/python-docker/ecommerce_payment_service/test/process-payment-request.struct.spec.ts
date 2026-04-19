import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ProcessPaymentRequest } from '../src/dto/process-payment-request.struct';
import { PaymentMethod } from '../src/enums/payment-method.enum';

describe('ProcessPaymentRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      orderId: '550e8400-e29b-41d4-a716-446655440000',
      amount: 99.99,
      method: PaymentMethod.CreditCard,
      cardToken: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ProcessPaymentRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.orderId).toBeDefined();
    expect(instance.amount).toBeDefined();
    expect(instance.method).toBeDefined();
    expect(instance.cardToken).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ProcessPaymentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when orderId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.orderId;
    const instance = plainToInstance(ProcessPaymentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when amount is missing', async () => {
    const payload = buildValidPayload();
    delete payload.amount;
    const instance = plainToInstance(ProcessPaymentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when method is missing', async () => {
    const payload = buildValidPayload();
    delete payload.method;
    const instance = plainToInstance(ProcessPaymentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});

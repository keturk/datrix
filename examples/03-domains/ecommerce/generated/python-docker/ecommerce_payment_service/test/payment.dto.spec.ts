import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreatePaymentDto } from '../src/dto/create-payment.dto';
import { PaymentMethod } from '../src/enums/payment-method.enum';
import { PaymentStatus } from '../src/enums/payment-status.enum';

describe('CreatePaymentDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      orderId: '550e8400-e29b-41d4-a716-446655440000',
      customerId: '550e8400-e29b-41d4-a716-446655440000',
      amount: 99.99,
      method: PaymentMethod.CreditCard,
      status: PaymentStatus.Pending,
      transactionId: `test-${Date.now()}`,
      gatewayResponse: 'test-value',
      errorMessage: 'test-value',
      processedAt: new Date('2025-01-15T12:00:00Z'),
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreatePaymentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when orderId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.orderId;
    const dto = plainToInstance(CreatePaymentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'orderId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when customerId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.customerId;
    const dto = plainToInstance(CreatePaymentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'customerId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when amount is missing', async () => {
    const payload = buildValidPayload();
    delete payload.amount;
    const dto = plainToInstance(CreatePaymentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'amount');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when method is missing', async () => {
    const payload = buildValidPayload();
    delete payload.method;
    const dto = plainToInstance(CreatePaymentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'method');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when transactionId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.transactionId;
    const dto = plainToInstance(CreatePaymentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'transactionId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when transactionId exceeds max length 100', async () => {
    const payload = buildValidPayload();
    payload.transactionId = 'x'.repeat(100 + 1);
    const dto = plainToInstance(CreatePaymentDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'transactionId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

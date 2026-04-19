import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateRefundDto } from '../src/dto/create-refund.dto';
import { PaymentStatus } from '../src/enums/payment-status.enum';

describe('CreateRefundDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      amount: 99.99,
      reason: 'test-value',
      status: PaymentStatus.Pending,
      refundTransactionId: 'test-value',
      errorMessage: 'test-value',
      processedAt: new Date('2025-01-15T12:00:00Z'),
      paymentId: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateRefundDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when amount is missing', async () => {
    const payload = buildValidPayload();
    delete payload.amount;
    const dto = plainToInstance(CreateRefundDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'amount');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when reason is missing', async () => {
    const payload = buildValidPayload();
    delete payload.reason;
    const dto = plainToInstance(CreateRefundDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'reason');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when paymentId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.paymentId;
    const dto = plainToInstance(CreateRefundDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'paymentId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when reason exceeds max length 500', async () => {
    const payload = buildValidPayload();
    payload.reason = 'x'.repeat(500 + 1);
    const dto = plainToInstance(CreateRefundDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'reason');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

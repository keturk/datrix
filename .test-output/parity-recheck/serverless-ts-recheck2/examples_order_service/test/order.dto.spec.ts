import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateOrderDto } from '../src/dto/create-order.dto';

describe('CreateOrderDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      id: '550e8400-e29b-41d4-a716-446655440000',
      amount: 10.50,
      currency: 'test-value',
      status: 'test-value',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when amount is missing', async () => {
    const payload = buildValidPayload();
    delete payload.amount;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'amount');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when currency is missing', async () => {
    const payload = buildValidPayload();
    delete payload.currency;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'currency');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when status is missing', async () => {
    const payload = buildValidPayload();
    delete payload.status;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'status');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

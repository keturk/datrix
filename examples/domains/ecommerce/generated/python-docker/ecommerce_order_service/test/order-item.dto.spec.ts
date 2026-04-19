import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateOrderItemDto } from '../src/dto/create-order-item.dto';

describe('CreateOrderItemDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      productId: '550e8400-e29b-41d4-a716-446655440000',
      productName: 'test-value',
      quantity: 42,
      unitPrice: 99.99,
      orderId: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateOrderItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when productId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.productId;
    const dto = plainToInstance(CreateOrderItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'productId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when productName is missing', async () => {
    const payload = buildValidPayload();
    delete payload.productName;
    const dto = plainToInstance(CreateOrderItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'productName');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when quantity is missing', async () => {
    const payload = buildValidPayload();
    delete payload.quantity;
    const dto = plainToInstance(CreateOrderItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'quantity');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when unitPrice is missing', async () => {
    const payload = buildValidPayload();
    delete payload.unitPrice;
    const dto = plainToInstance(CreateOrderItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'unitPrice');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when orderId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.orderId;
    const dto = plainToInstance(CreateOrderItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'orderId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when productName exceeds max length 200', async () => {
    const payload = buildValidPayload();
    payload.productName = 'x'.repeat(200 + 1);
    const dto = plainToInstance(CreateOrderItemDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'productName');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

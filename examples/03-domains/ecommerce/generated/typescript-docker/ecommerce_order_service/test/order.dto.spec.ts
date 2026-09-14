import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateOrderDto } from '../src/dto/create-order.dto';
import { OrderStatus } from '../src/enums/order-status.enum';
import { Address } from '../src/dto/address.struct';

describe('CreateOrderDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      customerId: '550e8400-e29b-41d4-a716-446655440000',
      orderNumber: `test-${Date.now()}`,
      status: OrderStatus.Pending,
      subtotal: 99.99,
      tax: 99.99,
      shippingCost: 99.99,
      discount: 99.99,
      shippingAddress: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      billingAddress: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      inventoryReservationId: '550e8400-e29b-41d4-a716-446655440000',
      paymentId: '550e8400-e29b-41d4-a716-446655440000',
      shipmentId: '550e8400-e29b-41d4-a716-446655440000',
      cancellationReason: 'test-value',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when customerId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.customerId;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'customerId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when orderNumber is missing', async () => {
    const payload = buildValidPayload();
    delete payload.orderNumber;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'orderNumber');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when subtotal is missing', async () => {
    const payload = buildValidPayload();
    delete payload.subtotal;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'subtotal');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when tax is missing', async () => {
    const payload = buildValidPayload();
    delete payload.tax;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'tax');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when shippingCost is missing', async () => {
    const payload = buildValidPayload();
    delete payload.shippingCost;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'shippingCost');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when discount is missing', async () => {
    const payload = buildValidPayload();
    delete payload.discount;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'discount');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when shippingAddress is missing', async () => {
    const payload = buildValidPayload();
    delete payload.shippingAddress;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'shippingAddress');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when billingAddress is missing', async () => {
    const payload = buildValidPayload();
    delete payload.billingAddress;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'billingAddress');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when inventoryReservationId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.inventoryReservationId;
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'inventoryReservationId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when orderNumber exceeds max length 20', async () => {
    const payload = buildValidPayload();
    payload.orderNumber = 'x'.repeat(20 + 1);
    const dto = plainToInstance(CreateOrderDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'orderNumber');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateShipmentItemDto } from '../src/dto/create-shipment-item.dto';

describe('CreateShipmentItemDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      productId: '550e8400-e29b-41d4-a716-446655440000',
      quantity: 42,
      shipmentId: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateShipmentItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when productId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.productId;
    const dto = plainToInstance(CreateShipmentItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'productId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when quantity is missing', async () => {
    const payload = buildValidPayload();
    delete payload.quantity;
    const dto = plainToInstance(CreateShipmentItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'quantity');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when shipmentId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.shipmentId;
    const dto = plainToInstance(CreateShipmentItemDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'shipmentId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

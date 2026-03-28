import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateShipmentDto } from '../src/dto/create-shipment.dto';
import { ShippingCarrier } from '../src/enums/shipping-carrier.enum';
import { ShipmentStatus } from '../src/enums/shipment-status.enum';
import { Address } from '../src/dto/address.struct';

describe('CreateShipmentDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      orderId: '550e8400-e29b-41d4-a716-446655440000',
      trackingNumber: `test-${Date.now()}`,
      carrier: ShippingCarrier.FedEx,
      status: ShipmentStatus.Pending,
      destination: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      weight: 10.50,
      estimatedDelivery: new Date('2025-01-15T12:00:00Z'),
      actualDelivery: new Date('2025-01-15T12:00:00Z'),
      failureReason: 'test-value',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateShipmentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when orderId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.orderId;
    const dto = plainToInstance(CreateShipmentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'orderId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when trackingNumber is missing', async () => {
    const payload = buildValidPayload();
    delete payload.trackingNumber;
    const dto = plainToInstance(CreateShipmentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'trackingNumber');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when carrier is missing', async () => {
    const payload = buildValidPayload();
    delete payload.carrier;
    const dto = plainToInstance(CreateShipmentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'carrier');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when destination is missing', async () => {
    const payload = buildValidPayload();
    delete payload.destination;
    const dto = plainToInstance(CreateShipmentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'destination');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when weight is missing', async () => {
    const payload = buildValidPayload();
    delete payload.weight;
    const dto = plainToInstance(CreateShipmentDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'weight');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when trackingNumber exceeds max length 50', async () => {
    const payload = buildValidPayload();
    payload.trackingNumber = 'x'.repeat(50 + 1);
    const dto = plainToInstance(CreateShipmentDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'trackingNumber');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

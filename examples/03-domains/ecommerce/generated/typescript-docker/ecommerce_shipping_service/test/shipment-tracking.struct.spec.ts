import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ShipmentTracking } from '../src/dto/shipment-tracking.struct';
import { ShipmentStatus } from '../src/enums/shipment-status.enum';
import { ShippingCarrier } from '../src/enums/shipping-carrier.enum';
import { Address } from '../src/dto/address.struct';

describe('ShipmentTracking Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      trackingNumber: 'test-value',
      status: ShipmentStatus.Pending,
      carrier: ShippingCarrier.FedEx,
      destination: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      estimatedDelivery: new Date('2025-01-15T12:00:00Z'),
      actualDelivery: new Date('2025-01-15T12:00:00Z'),
      events: [] as never[],
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ShipmentTracking, payload);
    expect(instance).toBeDefined();
    expect(instance.trackingNumber).toBeDefined();
    expect(instance.status).toBeDefined();
    expect(instance.carrier).toBeDefined();
    expect(instance.destination).toBeDefined();
    expect(instance.estimatedDelivery).toBeDefined();
    expect(instance.actualDelivery).toBeDefined();
    expect(instance.events).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ShipmentTracking, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when trackingNumber is missing', async () => {
    const payload = buildValidPayload();
    delete payload.trackingNumber;
    const instance = plainToInstance(ShipmentTracking, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when status is missing', async () => {
    const payload = buildValidPayload();
    delete payload.status;
    const instance = plainToInstance(ShipmentTracking, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when carrier is missing', async () => {
    const payload = buildValidPayload();
    delete payload.carrier;
    const instance = plainToInstance(ShipmentTracking, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when destination is missing', async () => {
    const payload = buildValidPayload();
    delete payload.destination;
    const instance = plainToInstance(ShipmentTracking, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when events is missing', async () => {
    const payload = buildValidPayload();
    delete payload.events;
    const instance = plainToInstance(ShipmentTracking, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});

import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateShipmentEventDto } from '../src/dto/create-shipment-event.dto';
import { ShipmentStatus } from '../src/enums/shipment-status.enum';

describe('CreateShipmentEventDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      timestamp: new Date('2025-01-15T12:00:00Z'),
      status: ShipmentStatus.Pending,
      location: 'test-value',
      description: 'test-text-content',
      shipmentId: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateShipmentEventDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when timestamp is missing', async () => {
    const payload = buildValidPayload();
    delete payload.timestamp;
    const dto = plainToInstance(CreateShipmentEventDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'timestamp');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when status is missing', async () => {
    const payload = buildValidPayload();
    delete payload.status;
    const dto = plainToInstance(CreateShipmentEventDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'status');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when location is missing', async () => {
    const payload = buildValidPayload();
    delete payload.location;
    const dto = plainToInstance(CreateShipmentEventDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'location');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when shipmentId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.shipmentId;
    const dto = plainToInstance(CreateShipmentEventDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'shipmentId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when location exceeds max length 200', async () => {
    const payload = buildValidPayload();
    payload.location = 'x'.repeat(200 + 1);
    const dto = plainToInstance(CreateShipmentEventDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'location');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

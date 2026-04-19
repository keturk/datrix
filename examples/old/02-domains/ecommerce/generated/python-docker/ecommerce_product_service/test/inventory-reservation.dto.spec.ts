import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateInventoryReservationDto } from '../src/dto/create-inventory-reservation.dto';
import { ReservationStatus } from '../src/enums/reservation-status.enum';

describe('CreateInventoryReservationDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      reservationId: '550e8400-e29b-41d4-a716-446655440000',
      quantity: 42,
      status: ReservationStatus.Reserved,
      expiresAt: new Date('2025-01-15T12:00:00Z'),
      productId: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateInventoryReservationDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when reservationId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.reservationId;
    const dto = plainToInstance(CreateInventoryReservationDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'reservationId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when quantity is missing', async () => {
    const payload = buildValidPayload();
    delete payload.quantity;
    const dto = plainToInstance(CreateInventoryReservationDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'quantity');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when expiresAt is missing', async () => {
    const payload = buildValidPayload();
    delete payload.expiresAt;
    const dto = plainToInstance(CreateInventoryReservationDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'expiresAt');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when productId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.productId;
    const dto = plainToInstance(CreateInventoryReservationDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'productId');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});

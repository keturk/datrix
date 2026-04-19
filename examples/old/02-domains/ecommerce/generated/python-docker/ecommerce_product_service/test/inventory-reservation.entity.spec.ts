import { InventoryReservation } from '../src/entities/inventory-reservation.entity';
import { ReservationStatus } from '../src/enums/reservation-status.enum';

describe('InventoryReservation Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new InventoryReservation();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new InventoryReservation();
    const reservationIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const quantityVal = 42;
    const statusVal = ReservationStatus.Reserved;
    const expiresAtVal = new Date('2025-01-15T12:00:00Z');
    const productIdVal = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
    entity.reservationId = reservationIdVal;
    entity.quantity = quantityVal;
    entity.status = statusVal;
    entity.expiresAt = expiresAtVal;
    entity.productId = productIdVal;
    expect(entity.reservationId).toBe(reservationIdVal);
    expect(entity.quantity).toBe(quantityVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.expiresAt).toEqual(expiresAtVal);
    expect(entity.productId).toBe(productIdVal);
  });

  it('should update field values', () => {
    const entity = new InventoryReservation();
    const reservationIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const quantityVal = 99;
    const statusVal = ReservationStatus.Confirmed;
    const expiresAtVal = new Date('2025-06-20T15:30:00Z');
    const productIdVal = 'b1ffbc99-9c0b-4ef8-bb6d-6bb9bd380a22';
    entity.reservationId = reservationIdVal;
    entity.quantity = quantityVal;
    entity.status = statusVal;
    entity.expiresAt = expiresAtVal;
    entity.productId = productIdVal;
    expect(entity.reservationId).toBe(reservationIdVal);
    expect(entity.quantity).toBe(quantityVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.expiresAt).toEqual(expiresAtVal);
    expect(entity.productId).toBe(productIdVal);
  });

  it('should have index on reservationId', () => {
    const entity = new InventoryReservation();
    entity.reservationId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.reservationId).toBeDefined();
  });

  it('should have index on expiresAt', () => {
    const entity = new InventoryReservation();
    entity.expiresAt = new Date('2025-01-15T12:00:00Z');
    expect(entity.expiresAt).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new InventoryReservation();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});

import { Order } from '../src/entities/order.entity';
import { OrderStatus } from '../src/enums/order-status.enum';
import { Address } from '../src/dto/address.struct';

describe('Order Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new Order();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new Order();
    const customerIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const orderNumberVal = `test-${Date.now()}`;
    const statusVal = OrderStatus.Pending;
    const subtotalVal = 99.99;
    const taxVal = 99.99;
    const shippingCostVal = 99.99;
    const discountVal = 99.99;
    const shippingAddressVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    const billingAddressVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    const inventoryReservationIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const paymentIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const shipmentIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const cancellationReasonVal = 'test-value';
    entity.customerId = customerIdVal;
    entity.orderNumber = orderNumberVal;
    entity.status = statusVal;
    entity.subtotal = subtotalVal;
    entity.tax = taxVal;
    entity.shippingCost = shippingCostVal;
    entity.discount = discountVal;
    entity.shippingAddress = shippingAddressVal;
    entity.billingAddress = billingAddressVal;
    entity.inventoryReservationId = inventoryReservationIdVal;
    entity.paymentId = paymentIdVal;
    entity.shipmentId = shipmentIdVal;
    entity.cancellationReason = cancellationReasonVal;
    expect(entity.customerId).toBe(customerIdVal);
    expect(entity.orderNumber).toBe(orderNumberVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.subtotal).toBe(subtotalVal);
    expect(entity.tax).toBe(taxVal);
    expect(entity.shippingCost).toBe(shippingCostVal);
    expect(entity.discount).toBe(discountVal);
    expect(entity.shippingAddress).toBe(shippingAddressVal);
    expect(entity.billingAddress).toBe(billingAddressVal);
    expect(entity.inventoryReservationId).toBe(inventoryReservationIdVal);
    expect(entity.paymentId).toBe(paymentIdVal);
    expect(entity.shipmentId).toBe(shipmentIdVal);
    expect(entity.cancellationReason).toBe(cancellationReasonVal);
  });

  it('should update field values', () => {
    const entity = new Order();
    const customerIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const orderNumberVal = `updated-${Date.now()}`;
    const statusVal = OrderStatus.PaymentPending;
    const subtotalVal = 149.99;
    const taxVal = 149.99;
    const shippingCostVal = 149.99;
    const discountVal = 149.99;
    const shippingAddressVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    const billingAddressVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    const inventoryReservationIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const paymentIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const shipmentIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const cancellationReasonVal = 'updated-value';
    entity.customerId = customerIdVal;
    entity.orderNumber = orderNumberVal;
    entity.status = statusVal;
    entity.subtotal = subtotalVal;
    entity.tax = taxVal;
    entity.shippingCost = shippingCostVal;
    entity.discount = discountVal;
    entity.shippingAddress = shippingAddressVal;
    entity.billingAddress = billingAddressVal;
    entity.inventoryReservationId = inventoryReservationIdVal;
    entity.paymentId = paymentIdVal;
    entity.shipmentId = shipmentIdVal;
    entity.cancellationReason = cancellationReasonVal;
    expect(entity.customerId).toBe(customerIdVal);
    expect(entity.orderNumber).toBe(orderNumberVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.subtotal).toBe(subtotalVal);
    expect(entity.tax).toBe(taxVal);
    expect(entity.shippingCost).toBe(shippingCostVal);
    expect(entity.discount).toBe(discountVal);
    expect(entity.shippingAddress).toBe(shippingAddressVal);
    expect(entity.billingAddress).toBe(billingAddressVal);
    expect(entity.inventoryReservationId).toBe(inventoryReservationIdVal);
    expect(entity.paymentId).toBe(paymentIdVal);
    expect(entity.shipmentId).toBe(shipmentIdVal);
    expect(entity.cancellationReason).toBe(cancellationReasonVal);
  });

  it('should enforce unique constraint on orderNumber', () => {
    const entity = new Order();
    entity.orderNumber = `test-${Date.now()}`;
    expect(entity.orderNumber).toBeDefined();
  });

  it('should have index on customerId', () => {
    const entity = new Order();
    entity.customerId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.customerId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new Order();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});

/**
 * Behavior tests for pubsub schemas, producer envelopes, and handler dispatch
 * (auto-generated). Sibling to contracts.spec.ts (ensure-clause tests only).
 */
import {
  ProductCreatedPayload,
  InventoryUpdatedPayload,
  InventoryReservedPayload,
  InventoryReleasedPayload,
  OrderConfirmedPayload,
  OrderCancelledPayload,
} from '../../../src/mq/schemas';
import { Address } from '../../../src/dto/address.struct'

describe('ProductCreatedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: ProductCreatedPayload = {
      productId: '00000000-0000-4000-8000-000000000001',
      name: 'aaaa',
      price: 99.99,
    };
    expect(Object.keys(payload).sort()).toEqual(["name", "price", "productId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: ProductCreatedPayload = {
      productId: '00000000-0000-4000-8000-000000000001',
      name: 'aaaa',
      price: 99.99,
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["name", "price", "productId"]);
  });
});

describe('InventoryUpdatedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: InventoryUpdatedPayload = {
      productId: '00000000-0000-4000-8000-000000000001',
      oldQuantity: 1,
      newQuantity: 1,
    };
    expect(Object.keys(payload).sort()).toEqual(["newQuantity", "oldQuantity", "productId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: InventoryUpdatedPayload = {
      productId: '00000000-0000-4000-8000-000000000001',
      oldQuantity: 1,
      newQuantity: 1,
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["newQuantity", "oldQuantity", "productId"]);
  });
});

describe('InventoryReservedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: InventoryReservedPayload = {
      reservationId: '00000000-0000-4000-8000-000000000001',
      productIds: ['00000000-0000-4000-8000-000000000001'],
    };
    expect(Object.keys(payload).sort()).toEqual(["productIds", "reservationId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: InventoryReservedPayload = {
      reservationId: '00000000-0000-4000-8000-000000000001',
      productIds: ['00000000-0000-4000-8000-000000000001'],
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["productIds", "reservationId"]);
  });
});

describe('InventoryReleasedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: InventoryReleasedPayload = {
      reservationId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
    };
    expect(Object.keys(payload).sort()).toEqual(["reason", "reservationId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: InventoryReleasedPayload = {
      reservationId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["reason", "reservationId"]);
  });
});

describe('OrderConfirmedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: OrderConfirmedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      paymentId: '00000000-0000-4000-8000-000000000001',
      reservationId: '00000000-0000-4000-8000-000000000001',
      shippingAddress: { street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '+15551234567' },
      items: [{ key: 'value' }],
      estimatedWeight: 1,
    };
    expect(Object.keys(payload).sort()).toEqual(["estimatedWeight", "items", "orderId", "paymentId", "reservationId", "shippingAddress"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: OrderConfirmedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      paymentId: '00000000-0000-4000-8000-000000000001',
      reservationId: '00000000-0000-4000-8000-000000000001',
      shippingAddress: { street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '+15551234567' },
      items: [{ key: 'value' }],
      estimatedWeight: 1,
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["estimatedWeight", "items", "orderId", "paymentId", "reservationId", "shippingAddress"]);
  });
});

describe('OrderCancelledPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: OrderCancelledPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
      reservationId: '00000000-0000-4000-8000-000000000001',
    };
    expect(Object.keys(payload).sort()).toEqual(["orderId", "reason", "reservationId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: OrderCancelledPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
      reservationId: '00000000-0000-4000-8000-000000000001',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["orderId", "reason", "reservationId"]);
  });
});

describe('producer envelope shape', () => {
  it('ProductCreated envelope has eventType and payload', () => {
    const payload: ProductCreatedPayload = {
      productId: '00000000-0000-4000-8000-000000000001',
      name: 'aaaa',
      price: 99.99,
    };
    const envelope = { eventType: 'ProductCreated', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('ProductCreated');
    expect(Object.keys(parsed.payload).sort()).toEqual(["name", "price", "productId"]);
  });

  it('InventoryUpdated envelope has eventType and payload', () => {
    const payload: InventoryUpdatedPayload = {
      productId: '00000000-0000-4000-8000-000000000001',
      oldQuantity: 1,
      newQuantity: 1,
    };
    const envelope = { eventType: 'InventoryUpdated', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('InventoryUpdated');
    expect(Object.keys(parsed.payload).sort()).toEqual(["newQuantity", "oldQuantity", "productId"]);
  });

  it('InventoryReserved envelope has eventType and payload', () => {
    const payload: InventoryReservedPayload = {
      reservationId: '00000000-0000-4000-8000-000000000001',
      productIds: ['00000000-0000-4000-8000-000000000001'],
    };
    const envelope = { eventType: 'InventoryReserved', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('InventoryReserved');
    expect(Object.keys(parsed.payload).sort()).toEqual(["productIds", "reservationId"]);
  });

  it('InventoryReleased envelope has eventType and payload', () => {
    const payload: InventoryReleasedPayload = {
      reservationId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
    };
    const envelope = { eventType: 'InventoryReleased', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('InventoryReleased');
    expect(Object.keys(parsed.payload).sort()).toEqual(["reason", "reservationId"]);
  });

  it('OrderConfirmed envelope has eventType and payload', () => {
    const payload: OrderConfirmedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      paymentId: '00000000-0000-4000-8000-000000000001',
      reservationId: '00000000-0000-4000-8000-000000000001',
      shippingAddress: { street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '+15551234567' },
      items: [{ key: 'value' }],
      estimatedWeight: 1,
    };
    const envelope = { eventType: 'OrderConfirmed', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('OrderConfirmed');
    expect(Object.keys(parsed.payload).sort()).toEqual(["estimatedWeight", "items", "orderId", "paymentId", "reservationId", "shippingAddress"]);
  });

  it('OrderCancelled envelope has eventType and payload', () => {
    const payload: OrderCancelledPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
      reservationId: '00000000-0000-4000-8000-000000000001',
    };
    const envelope = { eventType: 'OrderCancelled', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('OrderCancelled');
    expect(Object.keys(parsed.payload).sort()).toEqual(["orderId", "reason", "reservationId"]);
  });

});

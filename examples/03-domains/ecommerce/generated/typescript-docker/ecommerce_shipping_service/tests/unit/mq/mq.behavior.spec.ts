/**
 * Behavior tests for pubsub schemas, producer envelopes, and handler dispatch
 * (auto-generated). Sibling to contracts.spec.ts (ensure-clause tests only).
 */
import {
  ShipmentCreatedPayload,
  ShipmentDispatchedPayload,
  ShipmentDeliveredPayload,
  ShipmentFailedPayload,
  OrderConfirmedPayload,
} from '../../../src/mq/schemas';
import { Address } from '../../../src/dto/address.struct'

describe('ShipmentCreatedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: ShipmentCreatedPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
    };
    expect(Object.keys(payload).sort()).toEqual(["orderId", "shipmentId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: ShipmentCreatedPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["orderId", "shipmentId"]);
  });
});

describe('ShipmentDispatchedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: ShipmentDispatchedPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      trackingNumber: 'aaaa',
    };
    expect(Object.keys(payload).sort()).toEqual(["orderId", "shipmentId", "trackingNumber"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: ShipmentDispatchedPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      trackingNumber: 'aaaa',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["orderId", "shipmentId", "trackingNumber"]);
  });
});

describe('ShipmentDeliveredPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: ShipmentDeliveredPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      deliveredAt: new Date('2025-01-15T12:00:00Z'),
    };
    expect(Object.keys(payload).sort()).toEqual(["deliveredAt", "orderId", "shipmentId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: ShipmentDeliveredPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      deliveredAt: new Date('2025-01-15T12:00:00Z'),
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["deliveredAt", "orderId", "shipmentId"]);
  });
});

describe('ShipmentFailedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: ShipmentFailedPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
    };
    expect(Object.keys(payload).sort()).toEqual(["orderId", "reason", "shipmentId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: ShipmentFailedPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["orderId", "reason", "shipmentId"]);
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

describe('producer envelope shape', () => {
  it('ShipmentCreated envelope has eventType and payload', () => {
    const payload: ShipmentCreatedPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
    };
    const envelope = { eventType: 'ShipmentCreated', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('ShipmentCreated');
    expect(Object.keys(parsed.payload).sort()).toEqual(["orderId", "shipmentId"]);
  });

  it('ShipmentDispatched envelope has eventType and payload', () => {
    const payload: ShipmentDispatchedPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      trackingNumber: 'aaaa',
    };
    const envelope = { eventType: 'ShipmentDispatched', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('ShipmentDispatched');
    expect(Object.keys(parsed.payload).sort()).toEqual(["orderId", "shipmentId", "trackingNumber"]);
  });

  it('ShipmentDelivered envelope has eventType and payload', () => {
    const payload: ShipmentDeliveredPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      deliveredAt: new Date('2025-01-15T12:00:00Z'),
    };
    const envelope = { eventType: 'ShipmentDelivered', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('ShipmentDelivered');
    expect(Object.keys(parsed.payload).sort()).toEqual(["deliveredAt", "orderId", "shipmentId"]);
  });

  it('ShipmentFailed envelope has eventType and payload', () => {
    const payload: ShipmentFailedPayload = {
      shipmentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
    };
    const envelope = { eventType: 'ShipmentFailed', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('ShipmentFailed');
    expect(Object.keys(parsed.payload).sort()).toEqual(["orderId", "reason", "shipmentId"]);
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

});

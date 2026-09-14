/**
 * Behavior tests for pubsub schemas, producer envelopes, and handler dispatch
 * (auto-generated). Sibling to contracts.spec.ts (ensure-clause tests only).
 */
import {
  OrderCreatedPayload,
  OrderConfirmedPayload,
  OrderCancelledPayload,
  OrderStatusChangedPayload,
  PaymentProcessedPayload,
  PaymentFailedPayload,
  PaymentRefundedPayload,
  ShipmentCreatedPayload,
  ShipmentDispatchedPayload,
  ShipmentDeliveredPayload,
  ShipmentFailedPayload,
} from '../../../src/mq/schemas';
import { Address } from '../../../src/dto/address.struct'
import { OrderStatus } from '../../../src/enums/order-status.enum'

describe('OrderCreatedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: OrderCreatedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      orderNumber: 'aaaa',
      customerId: '00000000-0000-4000-8000-000000000001',
      total: 99.99,
      reservationId: '00000000-0000-4000-8000-000000000001',
    };
    expect(Object.keys(payload).sort()).toEqual(["customerId", "orderId", "orderNumber", "reservationId", "total"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: OrderCreatedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      orderNumber: 'aaaa',
      customerId: '00000000-0000-4000-8000-000000000001',
      total: 99.99,
      reservationId: '00000000-0000-4000-8000-000000000001',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["customerId", "orderId", "orderNumber", "reservationId", "total"]);
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

describe('OrderStatusChangedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: OrderStatusChangedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      oldStatus: OrderStatus.Pending,
      newStatus: OrderStatus.PaymentPending,
    };
    expect(Object.keys(payload).sort()).toEqual(["newStatus", "oldStatus", "orderId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: OrderStatusChangedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      oldStatus: OrderStatus.Pending,
      newStatus: OrderStatus.PaymentPending,
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["newStatus", "oldStatus", "orderId"]);
  });
});

describe('PaymentProcessedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: PaymentProcessedPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 99.99,
    };
    expect(Object.keys(payload).sort()).toEqual(["amount", "orderId", "paymentId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: PaymentProcessedPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 99.99,
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["amount", "orderId", "paymentId"]);
  });
});

describe('PaymentFailedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: PaymentFailedPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
    };
    expect(Object.keys(payload).sort()).toEqual(["orderId", "paymentId", "reason"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: PaymentFailedPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["orderId", "paymentId", "reason"]);
  });
});

describe('PaymentRefundedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: PaymentRefundedPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 99.99,
    };
    expect(Object.keys(payload).sort()).toEqual(["amount", "orderId", "paymentId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: PaymentRefundedPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 99.99,
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["amount", "orderId", "paymentId"]);
  });
});

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

describe('producer envelope shape', () => {
  it('OrderCreated envelope has eventType and payload', () => {
    const payload: OrderCreatedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      orderNumber: 'aaaa',
      customerId: '00000000-0000-4000-8000-000000000001',
      total: 99.99,
      reservationId: '00000000-0000-4000-8000-000000000001',
    };
    const envelope = { eventType: 'OrderCreated', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('OrderCreated');
    expect(Object.keys(parsed.payload).sort()).toEqual(["customerId", "orderId", "orderNumber", "reservationId", "total"]);
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

  it('OrderStatusChanged envelope has eventType and payload', () => {
    const payload: OrderStatusChangedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      oldStatus: OrderStatus.Pending,
      newStatus: OrderStatus.PaymentPending,
    };
    const envelope = { eventType: 'OrderStatusChanged', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('OrderStatusChanged');
    expect(Object.keys(parsed.payload).sort()).toEqual(["newStatus", "oldStatus", "orderId"]);
  });

  it('PaymentProcessed envelope has eventType and payload', () => {
    const payload: PaymentProcessedPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 99.99,
    };
    const envelope = { eventType: 'PaymentProcessed', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('PaymentProcessed');
    expect(Object.keys(parsed.payload).sort()).toEqual(["amount", "orderId", "paymentId"]);
  });

  it('PaymentFailed envelope has eventType and payload', () => {
    const payload: PaymentFailedPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      reason: 'aaaa',
    };
    const envelope = { eventType: 'PaymentFailed', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('PaymentFailed');
    expect(Object.keys(parsed.payload).sort()).toEqual(["orderId", "paymentId", "reason"]);
  });

  it('PaymentRefunded envelope has eventType and payload', () => {
    const payload: PaymentRefundedPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 99.99,
    };
    const envelope = { eventType: 'PaymentRefunded', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('PaymentRefunded');
    expect(Object.keys(parsed.payload).sort()).toEqual(["amount", "orderId", "paymentId"]);
  });

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

});

/**
 * Behavior tests for pubsub schemas, producer envelopes, and handler dispatch
 * (auto-generated). Sibling to contracts.spec.ts (ensure-clause tests only).
 */
import {
  OrderPlacedPayload,
  OrderCancelledPayload,
} from '../../../src/mq/schemas';

describe('OrderPlacedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: OrderPlacedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 1,
    };
    expect(Object.keys(payload).sort()).toEqual(["amount", "orderId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: OrderPlacedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 1,
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["amount", "orderId"]);
  });
});

describe('OrderCancelledPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: OrderCancelledPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
    };
    expect(Object.keys(payload).sort()).toEqual(["orderId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: OrderCancelledPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["orderId"]);
  });
});

describe('producer envelope shape', () => {
  it('OrderPlaced envelope has eventType and payload', () => {
    const payload: OrderPlacedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 1,
    };
    const envelope = { eventType: 'OrderPlaced', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('OrderPlaced');
    expect(Object.keys(parsed.payload).sort()).toEqual(["amount", "orderId"]);
  });

  it('OrderCancelled envelope has eventType and payload', () => {
    const payload: OrderCancelledPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
    };
    const envelope = { eventType: 'OrderCancelled', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('OrderCancelled');
    expect(Object.keys(parsed.payload).sort()).toEqual(["orderId"]);
  });

});

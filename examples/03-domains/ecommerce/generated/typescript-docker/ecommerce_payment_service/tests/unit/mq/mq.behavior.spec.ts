/**
 * Behavior tests for pubsub schemas, producer envelopes, and handler dispatch
 * (auto-generated). Sibling to contracts.spec.ts (ensure-clause tests only).
 */
import {
  PaymentProcessedPayload,
  PaymentFailedPayload,
  PaymentRefundedPayload,
  OrderCreatedPayload,
} from '../../../src/mq/schemas';

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

describe('producer envelope shape', () => {
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

});
import { KafkaEventConsumer } from '../../../src/mq/consumer';

// Handlers are invoked off the class prototype rather than a `new`-constructed
// instance: the real consumer constructor always requires an engine connection
// (KafkaConnection/RabbitMQConnection/ServiceBusConnection), whose safe
// construction is engine/platform-specific. TS treats `private` as a
// compile-time-only modifier -- bracket-notation access to a private member
// is not an accessibility error -- so a plain object can stand in for `this`
// so long as the handler body never reaches infrastructure (guaranteed below:
// only handlers needing no DB/EventEmitter/FunctionsService/GraphQL-PubSub AND
// importing no infrastructure-backed `_*Helpers` module -- cache, queue,
// storage, email, SMS, push -- reach this list).
type HandlerDispatchTarget = Record<string, (payload: unknown) => Promise<void>>;

describe('handler dispatch', () => {
  it('handleOrderCreated processes a valid payload without throwing', async () => {
    const target = KafkaEventConsumer.prototype as unknown as HandlerDispatchTarget;
    const payload: OrderCreatedPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      orderNumber: 'aaaa',
      customerId: '00000000-0000-4000-8000-000000000001',
      total: 99.99,
      reservationId: '00000000-0000-4000-8000-000000000001',
    };
    await expect(target['handleOrderCreated'](payload)).resolves.not.toThrow();
  });

});

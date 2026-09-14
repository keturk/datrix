/**
 * Tests for queue payload interfaces (auto-generated).
 *
 * TypeScript `interface` members have no runtime representation to assert
 * immutability against (unlike a frozen dataclass) -- `readonly` is a
 * compile-time-only guarantee already enforced by `tsc --noEmit` on the
 * interface declaration itself (see `queue_payloads.ts.j2`), so this file
 * does not port a runtime "payload is frozen" test.
 */
import type {
  ProcessPaymentPayload,
  SendOrderConfirmationPayload,
  SettlePaymentPayload,
} from '../../../src/queue/payloads';

describe('ProcessPaymentPayload', () => {
  it('constructs with exactly the declared fields', () => {
    const payload: ProcessPaymentPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 99.99,
      currency: 'aaa',
    };
    expect(Object.keys(payload).sort()).toEqual(["amount", "currency", "orderId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: ProcessPaymentPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      amount: 99.99,
      currency: 'aaa',
    };
    const serialized = JSON.stringify(payload);
    const deserialized = JSON.parse(serialized) as Record<string, unknown>;
    expect(Object.keys(deserialized).sort()).toEqual(["amount", "currency", "orderId"]);
  });
});

describe('SendOrderConfirmationPayload', () => {
  it('constructs with exactly the declared fields', () => {
    const payload: SendOrderConfirmationPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      customerEmail: 'aaaaaaaaaaaaaaaa',
      orderNumber: 'test',
    };
    expect(Object.keys(payload).sort()).toEqual(["customerEmail", "orderId", "orderNumber"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: SendOrderConfirmationPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
      customerEmail: 'aaaaaaaaaaaaaaaa',
      orderNumber: 'test',
    };
    const serialized = JSON.stringify(payload);
    const deserialized = JSON.parse(serialized) as Record<string, unknown>;
    expect(Object.keys(deserialized).sort()).toEqual(["customerEmail", "orderId", "orderNumber"]);
  });
});

describe('SettlePaymentPayload', () => {
  it('constructs with exactly the declared fields', () => {
    const payload: SettlePaymentPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      merchantId: 'aaaa',
      amount: 1,
    };
    expect(Object.keys(payload).sort()).toEqual(["amount", "merchantId", "paymentId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: SettlePaymentPayload = {
      paymentId: '00000000-0000-4000-8000-000000000001',
      merchantId: 'aaaa',
      amount: 1,
    };
    const serialized = JSON.stringify(payload);
    const deserialized = JSON.parse(serialized) as Record<string, unknown>;
    expect(Object.keys(deserialized).sort()).toEqual(["amount", "merchantId", "paymentId"]);
  });
});


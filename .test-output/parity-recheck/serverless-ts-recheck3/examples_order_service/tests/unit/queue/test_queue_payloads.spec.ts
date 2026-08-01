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
  ProcessShipmentPayload,
} from '../../../src/queue/payloads';

describe('ProcessShipmentPayload', () => {
  it('constructs with exactly the declared fields', () => {
    const payload: ProcessShipmentPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
    };
    expect(Object.keys(payload).sort()).toEqual(["orderId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: ProcessShipmentPayload = {
      orderId: '00000000-0000-4000-8000-000000000001',
    };
    const serialized = JSON.stringify(payload);
    const deserialized = JSON.parse(serialized) as Record<string, unknown>;
    expect(Object.keys(deserialized).sort()).toEqual(["orderId"]);
  });
});


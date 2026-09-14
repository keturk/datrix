/**
 * Behavior tests for pubsub schemas, producer envelopes, and handler dispatch
 * (auto-generated). Sibling to contracts.spec.ts (ensure-clause tests only).
 */
import {
  UserRegisteredPayload,
  UserVerifiedPayload,
  UserStatusChangedPayload,
  UserLoggedInPayload,
} from '../../../src/mq/schemas';
import { UserStatus } from '../../../src/enums/user-status.enum'

describe('UserRegisteredPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: UserRegisteredPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      email: 'user@example.com',
      fullName: 'aaaa',
    };
    expect(Object.keys(payload).sort()).toEqual(["email", "fullName", "userId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: UserRegisteredPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      email: 'user@example.com',
      fullName: 'aaaa',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["email", "fullName", "userId"]);
  });
});

describe('UserVerifiedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: UserVerifiedPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      email: 'user@example.com',
    };
    expect(Object.keys(payload).sort()).toEqual(["email", "userId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: UserVerifiedPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      email: 'user@example.com',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["email", "userId"]);
  });
});

describe('UserStatusChangedPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: UserStatusChangedPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      oldStatus: UserStatus.Active,
      newStatus: UserStatus.Inactive,
    };
    expect(Object.keys(payload).sort()).toEqual(["newStatus", "oldStatus", "userId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: UserStatusChangedPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      oldStatus: UserStatus.Active,
      newStatus: UserStatus.Inactive,
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["newStatus", "oldStatus", "userId"]);
  });
});

describe('UserLoggedInPayload', () => {
  it('has exactly the declared field names', () => {
    const payload: UserLoggedInPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      loginAt: new Date('2025-01-15T12:00:00Z'),
      ipAddress: 'test',
    };
    expect(Object.keys(payload).sort()).toEqual(["ipAddress", "loginAt", "userId"]);
  });

  it('round-trips through JSON without losing any field', () => {
    const payload: UserLoggedInPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      loginAt: new Date('2025-01-15T12:00:00Z'),
      ipAddress: 'test',
    };
    const restored = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
    expect(Object.keys(restored).sort()).toEqual(["ipAddress", "loginAt", "userId"]);
  });
});

describe('producer envelope shape', () => {
  it('UserRegistered envelope has eventType and payload', () => {
    const payload: UserRegisteredPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      email: 'user@example.com',
      fullName: 'aaaa',
    };
    const envelope = { eventType: 'UserRegistered', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('UserRegistered');
    expect(Object.keys(parsed.payload).sort()).toEqual(["email", "fullName", "userId"]);
  });

  it('UserVerified envelope has eventType and payload', () => {
    const payload: UserVerifiedPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      email: 'user@example.com',
    };
    const envelope = { eventType: 'UserVerified', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('UserVerified');
    expect(Object.keys(parsed.payload).sort()).toEqual(["email", "userId"]);
  });

  it('UserStatusChanged envelope has eventType and payload', () => {
    const payload: UserStatusChangedPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      oldStatus: UserStatus.Active,
      newStatus: UserStatus.Inactive,
    };
    const envelope = { eventType: 'UserStatusChanged', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('UserStatusChanged');
    expect(Object.keys(parsed.payload).sort()).toEqual(["newStatus", "oldStatus", "userId"]);
  });

  it('UserLoggedIn envelope has eventType and payload', () => {
    const payload: UserLoggedInPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      loginAt: new Date('2025-01-15T12:00:00Z'),
      ipAddress: 'test',
    };
    const envelope = { eventType: 'UserLoggedIn', payload };
    const parsed = JSON.parse(JSON.stringify(envelope)) as {
      eventType: string;
      payload: Record<string, unknown>;
    };
    expect(parsed.eventType).toBe('UserLoggedIn');
    expect(Object.keys(parsed.payload).sort()).toEqual(["ipAddress", "loginAt", "userId"]);
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
  it('handleUserRegistered processes a valid payload without throwing', async () => {
    const target = KafkaEventConsumer.prototype as unknown as HandlerDispatchTarget;
    const payload: UserRegisteredPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      email: 'user@example.com',
      fullName: 'aaaa',
    };
    await expect(target['handleUserRegistered'](payload)).resolves.not.toThrow();
  });

  it('handleUserVerified processes a valid payload without throwing', async () => {
    const target = KafkaEventConsumer.prototype as unknown as HandlerDispatchTarget;
    const payload: UserVerifiedPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      email: 'user@example.com',
    };
    await expect(target['handleUserVerified'](payload)).resolves.not.toThrow();
  });

  it('handleUserStatusChanged processes a valid payload without throwing', async () => {
    const target = KafkaEventConsumer.prototype as unknown as HandlerDispatchTarget;
    const payload: UserStatusChangedPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      oldStatus: UserStatus.Active,
      newStatus: UserStatus.Inactive,
    };
    await expect(target['handleUserStatusChanged'](payload)).resolves.not.toThrow();
  });

  it('handleUserLoggedIn processes a valid payload without throwing', async () => {
    const target = KafkaEventConsumer.prototype as unknown as HandlerDispatchTarget;
    const payload: UserLoggedInPayload = {
      userId: '00000000-0000-4000-8000-000000000001',
      loginAt: new Date('2025-01-15T12:00:00Z'),
      ipAddress: 'test',
    };
    await expect(target['handleUserLoggedIn'](payload)).resolves.not.toThrow();
  });

});

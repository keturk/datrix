import type { UserStatusChangedPayload } from '../mq/schemas';

export class UserStatusChangedEvent {
  constructor(public readonly payload: UserStatusChangedPayload) {}
}

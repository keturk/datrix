import type { UserRegisteredPayload } from '../mq/schemas';

export class UserRegisteredEvent {
  constructor(public readonly payload: UserRegisteredPayload) {}
}

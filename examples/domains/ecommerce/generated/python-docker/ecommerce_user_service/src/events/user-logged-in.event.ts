import type { UserLoggedInPayload } from '../mq/schemas';

export class UserLoggedInEvent {
  constructor(public readonly payload: UserLoggedInPayload) {}
}

import type { UserVerifiedPayload } from '../mq/schemas';

export class UserVerifiedEvent {
  constructor(public readonly payload: UserVerifiedPayload) {}
}

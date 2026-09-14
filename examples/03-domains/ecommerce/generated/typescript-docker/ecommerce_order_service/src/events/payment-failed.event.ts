import type { PaymentFailedPayload } from '../mq/schemas';

export class PaymentFailedEvent {
  constructor(public readonly payload: PaymentFailedPayload) {}
}

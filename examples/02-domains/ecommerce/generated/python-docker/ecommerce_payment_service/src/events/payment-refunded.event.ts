import type { PaymentRefundedPayload } from '../mq/schemas';

export class PaymentRefundedEvent {
  constructor(public readonly payload: PaymentRefundedPayload) {}
}

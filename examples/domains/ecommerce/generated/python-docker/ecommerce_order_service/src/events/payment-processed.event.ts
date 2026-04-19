import type { PaymentProcessedPayload } from '../mq/schemas';

export class PaymentProcessedEvent {
  constructor(public readonly payload: PaymentProcessedPayload) {}
}

import type { ProcessPaymentPayload } from '../queue/payloads';

export class ProcessPaymentEvent {
  constructor(public readonly payload: ProcessPaymentPayload) {}
}

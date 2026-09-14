import type { SettlePaymentPayload } from '../queue/payloads';

export class SettlePaymentEvent {
  constructor(public readonly payload: SettlePaymentPayload) {}
}

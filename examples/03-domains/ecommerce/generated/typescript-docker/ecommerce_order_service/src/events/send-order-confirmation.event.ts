import type { SendOrderConfirmationPayload } from '../queue/payloads';

export class SendOrderConfirmationEvent {
  constructor(public readonly payload: SendOrderConfirmationPayload) {}
}

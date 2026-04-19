import type { OrderConfirmedPayload } from '../mq/schemas';

export class OrderConfirmedEvent {
  constructor(public readonly payload: OrderConfirmedPayload) {}
}

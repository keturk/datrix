import type { OrderCancelledPayload } from '../mq/schemas';

export class OrderCancelledEvent {
  constructor(public readonly payload: OrderCancelledPayload) {}
}

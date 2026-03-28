import type { OrderCreatedPayload } from '../mq/schemas';

export class OrderCreatedEvent {
  constructor(public readonly payload: OrderCreatedPayload) {}
}

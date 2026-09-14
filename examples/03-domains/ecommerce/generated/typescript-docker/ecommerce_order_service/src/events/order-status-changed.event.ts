import type { OrderStatusChangedPayload } from '../mq/schemas';

export class OrderStatusChangedEvent {
  constructor(public readonly payload: OrderStatusChangedPayload) {}
}

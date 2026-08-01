import type { OrderPlacedPayload } from '../mq/schemas';

export class OrderPlacedEvent {
  constructor(public readonly payload: OrderPlacedPayload) {}
}

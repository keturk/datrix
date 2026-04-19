import type { ProductCreatedPayload } from '../mq/schemas';

export class ProductCreatedEvent {
  constructor(public readonly payload: ProductCreatedPayload) {}
}

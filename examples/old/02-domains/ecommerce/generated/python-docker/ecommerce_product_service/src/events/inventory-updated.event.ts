import type { InventoryUpdatedPayload } from '../mq/schemas';

export class InventoryUpdatedEvent {
  constructor(public readonly payload: InventoryUpdatedPayload) {}
}

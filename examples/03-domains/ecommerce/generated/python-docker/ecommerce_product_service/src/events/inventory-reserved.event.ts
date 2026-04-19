import type { InventoryReservedPayload } from '../mq/schemas';

export class InventoryReservedEvent {
  constructor(public readonly payload: InventoryReservedPayload) {}
}

import type { InventoryReleasedPayload } from '../mq/schemas';

export class InventoryReleasedEvent {
  constructor(public readonly payload: InventoryReleasedPayload) {}
}

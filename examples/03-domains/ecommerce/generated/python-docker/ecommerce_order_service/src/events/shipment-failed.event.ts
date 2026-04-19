import type { ShipmentFailedPayload } from '../mq/schemas';

export class ShipmentFailedEvent {
  constructor(public readonly payload: ShipmentFailedPayload) {}
}

import type { ShipmentCreatedPayload } from '../mq/schemas';

export class ShipmentCreatedEvent {
  constructor(public readonly payload: ShipmentCreatedPayload) {}
}

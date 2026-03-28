import type { ShipmentDispatchedPayload } from '../mq/schemas';

export class ShipmentDispatchedEvent {
  constructor(public readonly payload: ShipmentDispatchedPayload) {}
}

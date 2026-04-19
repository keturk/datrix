import type { ShipmentDeliveredPayload } from '../mq/schemas';

export class ShipmentDeliveredEvent {
  constructor(public readonly payload: ShipmentDeliveredPayload) {}
}

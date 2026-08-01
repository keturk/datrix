import type { ProcessShipmentPayload } from '../queue/payloads';

export class ProcessShipmentEvent {
  constructor(public readonly payload: ProcessShipmentPayload) {}
}

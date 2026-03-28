import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { ShipmentFailedEvent } from './shipment-failed.event';

@EventsHandler(ShipmentFailedEvent)
export class HandleShipmentFailedHandler implements IEventHandler<ShipmentFailedEvent> {
  private readonly logger = new Logger(HandleShipmentFailedHandler.name);

  async handle(event: ShipmentFailedEvent): Promise<void> {
console.warn('shipment_failed_for_order');;
  }
}

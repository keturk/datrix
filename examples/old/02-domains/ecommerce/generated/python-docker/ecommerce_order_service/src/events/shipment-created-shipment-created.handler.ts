import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { ShipmentCreatedEvent } from './shipment-created.event';

@EventsHandler(ShipmentCreatedEvent)
export class HandleShipmentCreatedHandler implements IEventHandler<ShipmentCreatedEvent> {
  private readonly logger = new Logger(HandleShipmentCreatedHandler.name);

  async handle(event: ShipmentCreatedEvent): Promise<void> {
console.info('shipment_created_for_order');;
  }
}

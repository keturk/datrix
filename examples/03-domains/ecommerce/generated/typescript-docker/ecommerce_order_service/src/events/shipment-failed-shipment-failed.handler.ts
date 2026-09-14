import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { ShipmentFailedEvent } from './shipment-failed.event';
import { EntityManager } from '@mikro-orm/core';

@EventsHandler(ShipmentFailedEvent)
export class HandleShipmentFailedHandler implements IEventHandler<ShipmentFailedEvent> {
  private readonly logger = new Logger(HandleShipmentFailedHandler.name);

  constructor(
    private readonly orderDbEm: EntityManager,
  ) {}

  async handle(event: ShipmentFailedEvent): Promise<void> {
console.warn('shipment_failed_for_order');
  }
}

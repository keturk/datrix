import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { InventoryReservedEvent } from './inventory-reserved.event';

@EventsHandler(InventoryReservedEvent)
export class HandleInventoryReservedHandler implements IEventHandler<InventoryReservedEvent> {
  private readonly logger = new Logger(HandleInventoryReservedHandler.name);

  async handle(event: InventoryReservedEvent): Promise<void> {
console.info('inventory_reserved');;
  }
}

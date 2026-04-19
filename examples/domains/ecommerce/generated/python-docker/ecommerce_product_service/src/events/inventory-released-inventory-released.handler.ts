import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { InventoryReleasedEvent } from './inventory-released.event';

@EventsHandler(InventoryReleasedEvent)
export class HandleInventoryReleasedHandler implements IEventHandler<InventoryReleasedEvent> {
  private readonly logger = new Logger(HandleInventoryReleasedHandler.name);

  async handle(event: InventoryReleasedEvent): Promise<void> {
console.info('inventory_released');;
  }
}

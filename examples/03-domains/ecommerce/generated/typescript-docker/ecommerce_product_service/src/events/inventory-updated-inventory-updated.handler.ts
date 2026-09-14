import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { InventoryUpdatedEvent } from './inventory-updated.event';
import { EntityManager } from '@mikro-orm/core';

@EventsHandler(InventoryUpdatedEvent)
export class HandleInventoryUpdatedHandler implements IEventHandler<InventoryUpdatedEvent> {
  private readonly logger = new Logger(HandleInventoryUpdatedHandler.name);

  constructor(
    private readonly productDbEm: EntityManager,
  ) {}

  async handle(event: InventoryUpdatedEvent): Promise<void> {
console.info('inventory_updated');
  }
}

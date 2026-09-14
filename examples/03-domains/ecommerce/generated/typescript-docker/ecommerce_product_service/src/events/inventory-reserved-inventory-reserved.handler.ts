import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { InventoryReservedEvent } from './inventory-reserved.event';
import { EntityManager } from '@mikro-orm/core';

@EventsHandler(InventoryReservedEvent)
export class HandleInventoryReservedHandler implements IEventHandler<InventoryReservedEvent> {
  private readonly logger = new Logger(HandleInventoryReservedHandler.name);

  constructor(
    private readonly productDbEm: EntityManager,
  ) {}

  async handle(event: InventoryReservedEvent): Promise<void> {
console.info('inventory_reserved');
  }
}

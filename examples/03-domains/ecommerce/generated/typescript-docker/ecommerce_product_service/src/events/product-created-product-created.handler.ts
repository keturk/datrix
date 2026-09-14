import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { ProductCreatedEvent } from './product-created.event';
import { EntityManager } from '@mikro-orm/core';

@EventsHandler(ProductCreatedEvent)
export class HandleProductCreatedHandler implements IEventHandler<ProductCreatedEvent> {
  private readonly logger = new Logger(HandleProductCreatedHandler.name);

  constructor(
    private readonly productDbEm: EntityManager,
  ) {}

  async handle(event: ProductCreatedEvent): Promise<void> {
console.info('product_created');
  }
}

import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { ProductCreatedEvent } from './product-created.event';

@EventsHandler(ProductCreatedEvent)
export class HandleProductCreatedHandler implements IEventHandler<ProductCreatedEvent> {
  private readonly logger = new Logger(HandleProductCreatedHandler.name);

  async handle(event: ProductCreatedEvent): Promise<void> {
console.info('product_created');;
  }
}

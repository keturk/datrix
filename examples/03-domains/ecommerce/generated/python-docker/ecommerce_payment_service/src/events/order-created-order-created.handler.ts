import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { OrderCreatedEvent } from './order-created.event';

@EventsHandler(OrderCreatedEvent)
export class HandleOrderCreatedHandler implements IEventHandler<OrderCreatedEvent> {
  private readonly logger = new Logger(HandleOrderCreatedHandler.name);

  async handle(event: OrderCreatedEvent): Promise<void> {
console.info('new_order_created_awaiting_payment');;
  }
}

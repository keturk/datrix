import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { OrderStatusChangedEvent } from './order-status-changed.event';
import { _getRedis } from '../ecommerce_order_service/_cacheHelpers';

@EventsHandler(OrderStatusChangedEvent)
export class HandleOrderStatusChangedHandler implements IEventHandler<OrderStatusChangedEvent> {
  private readonly logger = new Logger(HandleOrderStatusChangedHandler.name);

  async handle(event: OrderStatusChangedEvent): Promise<void> {
console.info('order_status_changed');;
    const cached: Record<string, unknown> | null = (JSON.parse(await _getRedis().get(`orderCache:${event.payload.orderId}`) ?? 'null') as unknown);
    if ((cached != null)) {
      await _getRedis().set(`orderCache:${event.payload.orderId}`, JSON.stringify({orderId: event.payload.orderId, orderNumber: cached.orderNumber, status: event.payload.newStatus, total: cached.total}));;
    }
  }
}

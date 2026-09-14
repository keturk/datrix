import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { OrderStatusChangedEvent } from './order-status-changed.event';
import { EntityManager } from '@mikro-orm/core';
import { _getRedis } from '../ecommerce_order_service/_cacheHelpers';

@EventsHandler(OrderStatusChangedEvent)
export class HandleOrderStatusChangedHandler implements IEventHandler<OrderStatusChangedEvent> {
  private readonly logger = new Logger(HandleOrderStatusChangedHandler.name);

  constructor(
    private readonly orderDbEm: EntityManager,
  ) {}

  async handle(event: OrderStatusChangedEvent): Promise<void> {
console.info('order_status_changed');
    // Keep cache in sync with order status changes
    let cached = (await (async () => {
      const _m = await _getRedis().hgetall((String("order:") + ':' + String(event.payload.orderId)));
      const out: Record<string, any> = {};
      for (const [k, v] of Object.entries(_m)) {
        out[k] = JSON.parse(String(v));
      }
      return out;
    })());
    if ((cached != null)) {
      (await Promise.all([_getRedis().hset((String("order:") + ':' + String(event.payload.orderId)), Object.fromEntries(Object.entries({orderId: event.payload.orderId, orderNumber: cached['orderNumber'], status: event.payload.newStatus, total: cached['total']}).map(([k, v]) => [String(k), JSON.stringify(v)]))), _getRedis().expire((String("order:") + ':' + String(event.payload.orderId)), 3600)]))[0];
    }
  }
}

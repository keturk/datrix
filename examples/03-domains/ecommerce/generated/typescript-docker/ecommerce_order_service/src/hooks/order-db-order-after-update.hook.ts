import type { EntityManager } from '@mikro-orm/core';
import { Order } from '../ecommerce_order_service/entities/order_db/order.entity';

import { OrderStatus } from '../enums/order-status.enum'
import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';
import { producerInstance as mqProducerInstance } from '../mq/producer';

export async function orderDbOrderAfterUpdate(
  target: Order,
  db: EntityManager,
  oldValues?: Record<string, unknown>,
): Promise<void> {
  if (_fieldChanged(target, "status", oldValues)) {
    if (mqProducerInstance !== null) {
    await mqProducerInstance.publishOrderStatusChanged({ orderId: target.id, oldStatus: _fieldOldValue(target, "status", oldValues) as OrderStatus, newStatus: target.status });
  }
    if ((target.status === OrderStatus.Confirmed)) {
      let orderItems: Record<string, any>[] = target.items.map((i) => ({productId: i.productId, quantity: i.quantity}));
      let estimatedWeight: number = (target.items.length * 1.0);
      if (mqProducerInstance !== null) {
    await mqProducerInstance.publishOrderConfirmed({ orderId: target.id, paymentId: target.paymentId!, reservationId: target.inventoryReservationId, shippingAddress: target.shippingAddress, items: orderItems, estimatedWeight: estimatedWeight });
  }
    } else if ((target.status === OrderStatus.Cancelled)) {
      if (mqProducerInstance !== null) {
    await mqProducerInstance.publishOrderCancelled({ orderId: target.id, reason: (target.cancellationReason ?? OrderStatus.Cancelled), reservationId: target.inventoryReservationId });
  }
    }
  }
}
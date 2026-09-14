import type { EntityManager } from '@mikro-orm/core';
import { Order } from '../ecommerce_order_service/entities/order_db/order.entity';

import axios from 'axios';
import { UserServiceUserResponse } from '../clients/user-service-responses';
import { producerInstance as mqProducerInstance } from '../mq/producer';
import { queueClientInstance } from '../queue/client';

export async function orderDbOrderAfterCreate(
  target: Order,
  db: EntityManager,
  oldValues?: Record<string, unknown>,
): Promise<void> {
  if (mqProducerInstance !== null) {
    await mqProducerInstance.publishOrderCreated({ orderId: target.id, orderNumber: target.orderNumber, customerId: target.customerId, total: target.total, reservationId: target.inventoryReservationId });
  }
  if (queueClientInstance !== null) {
    await queueClientInstance.dispatchProcessPayment(target.id, target.total, 'usd');
  }
  let u: UserServiceUserResponse = (await axios.get(`${String(process.env['SERVICE_ECOMMERCE_USER_SERVICE_URL'] ?? '').replace(/\/$/, '')}/${String(`/api/v1/service/${target.customerId}`).replace(/^\/+/, '')}`)).data;
  if (queueClientInstance !== null) {
    await queueClientInstance.dispatchSendOrderConfirmation(target.id, u['email'], target.orderNumber);
  }
}
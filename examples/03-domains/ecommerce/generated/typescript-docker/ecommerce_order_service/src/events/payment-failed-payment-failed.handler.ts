import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { PaymentFailedEvent } from './payment-failed.event';
import { EntityManager, EntityRepository } from '@mikro-orm/core';
import { InjectRepository } from '@mikro-orm/nestjs';
import { NotFoundException } from '@nestjs/common';
import { Order } from '../ecommerce_order_service/entities/order_db/order.entity';
import { OrderStatus } from '../enums/order-status.enum';
import { bufferEvents } from '../eventOutbox';

@EventsHandler(PaymentFailedEvent)
export class HandlePaymentFailedHandler implements IEventHandler<PaymentFailedEvent> {
  private readonly logger = new Logger(HandlePaymentFailedHandler.name);

  constructor(
    @InjectRepository(Order) private readonly orderRepository: EntityRepository<Order>,
    private readonly orderDbEm: EntityManager,
  ) {}

  async handle(event: PaymentFailedEvent): Promise<void> {
const order = await this.orderRepository.findOne({ id: event.payload.orderId });
    if (!order) {
      throw new NotFoundException("Not found");
    }
    await bufferEvents(async () => {
      await this.orderDbEm.transactional(async (manager: EntityManager) => {
      order.status = OrderStatus.Cancelled;
      order.cancellationReason = `Payment failed: ${event.payload.reason}`;
      await this.orderRepository.getEntityManager().persistAndFlush(order);
    });
    });
    console.warn('order_cancelled_due_to_payment_failure');
  }
}

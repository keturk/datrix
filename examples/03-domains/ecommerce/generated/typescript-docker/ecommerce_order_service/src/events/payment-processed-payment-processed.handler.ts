import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { PaymentProcessedEvent } from './payment-processed.event';
import { EntityManager, EntityRepository } from '@mikro-orm/core';
import { InjectRepository } from '@mikro-orm/nestjs';
import { NotFoundException } from '@nestjs/common';
import { Order } from '../ecommerce_order_service/entities/order_db/order.entity';
import { OrderStatus } from '../enums/order-status.enum';
import { bufferEvents } from '../eventOutbox';
import { queueClientInstance } from '../queue/client';

@EventsHandler(PaymentProcessedEvent)
export class HandlePaymentProcessedHandler implements IEventHandler<PaymentProcessedEvent> {
  private readonly logger = new Logger(HandlePaymentProcessedHandler.name);

  constructor(
    @InjectRepository(Order) private readonly orderRepository: EntityRepository<Order>,
    private readonly orderDbEm: EntityManager,
  ) {}

  async handle(event: PaymentProcessedEvent): Promise<void> {
const order = await this.orderRepository.findOne({ id: event.payload.orderId });
    if (!order) {
      throw new NotFoundException("Not found");
    }
    await bufferEvents(async () => {
      await this.orderDbEm.transactional(async (manager: EntityManager) => {
      order.paymentId = event.payload.paymentId;
      order.status = OrderStatus.Confirmed;
      await this.orderRepository.getEntityManager().persistAndFlush(order);
    });
    });
    console.info('order_confirmed_after_payment');
    if (queueClientInstance !== null) {
      await queueClientInstance.dispatchSettlePayment(event.payload.paymentId, 'ECOM-DEMO-MERCHANT', event.payload.amount);
    }
  }
}

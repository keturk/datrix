import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { PaymentRefundedEvent } from './payment-refunded.event';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { NotFoundException } from '@nestjs/common';
import { Order } from '../entities/order.entity';
import { OrderStatus } from '../enums/order-status.enum'

@EventsHandler(PaymentRefundedEvent)
export class HandlePaymentRefundedHandler implements IEventHandler<PaymentRefundedEvent> {
  private readonly logger = new Logger(HandlePaymentRefundedHandler.name);

  constructor(
    @InjectRepository(Order)
    private readonly orderRepository: Repository<Order>,
  ) {}

  async handle(event: PaymentRefundedEvent): Promise<void> {
const order = await this.orderRepository.findOneOrFail({ where: { id: event.payload.orderId } });
    await this.dbDataSource.transaction(async (manager: EntityManager) => {
      order.status = OrderStatus.Refunded;
      await this.orderRepository.save(order);
    });
    console.info('order_refunded_after_payment_refund');;
  }
}

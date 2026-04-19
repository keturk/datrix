import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { PaymentProcessedEvent } from './payment-processed.event';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { NotFoundException } from '@nestjs/common';
import { Order } from '../entities/order.entity';
import { OrderStatus } from '../enums/order-status.enum'

@EventsHandler(PaymentProcessedEvent)
export class HandlePaymentProcessedHandler implements IEventHandler<PaymentProcessedEvent> {
  private readonly logger = new Logger(HandlePaymentProcessedHandler.name);

  constructor(
    @InjectRepository(Order)
    private readonly orderRepository: Repository<Order>,
  ) {}

  async handle(event: PaymentProcessedEvent): Promise<void> {
const order = await this.orderRepository.findOneOrFail({ where: { id: event.payload.orderId } });
    await this.dbDataSource.transaction(async (manager: EntityManager) => {
      order.paymentId = event.payload.paymentId;
      order.status = OrderStatus.Confirmed;
      await this.orderRepository.save(order);
    });
    console.info('order_confirmed_after_payment');;
  }
}

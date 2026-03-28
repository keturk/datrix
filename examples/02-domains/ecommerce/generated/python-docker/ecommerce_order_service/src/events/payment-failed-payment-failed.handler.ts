import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { PaymentFailedEvent } from './payment-failed.event';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { NotFoundException } from '@nestjs/common';
import { Order } from '../entities/order.entity';
import { OrderStatus } from '../enums/order-status.enum'

@EventsHandler(PaymentFailedEvent)
export class HandlePaymentFailedHandler implements IEventHandler<PaymentFailedEvent> {
  private readonly logger = new Logger(HandlePaymentFailedHandler.name);

  constructor(
    @InjectRepository(Order)
    private readonly orderRepository: Repository<Order>,
  ) {}

  async handle(event: PaymentFailedEvent): Promise<void> {
const order = await this.orderRepository.findOneOrFail({ where: { id: event.payload.orderId } });
    await this.dbDataSource.transaction(async (manager: EntityManager) => {
      order.status = OrderStatus.Cancelled;
      order.cancellationReason = `Payment failed: ${event.payload.reason}`;
      await this.orderRepository.save(order);
    });
    console.warn('order_cancelled_due_to_payment_failure');;
  }
}

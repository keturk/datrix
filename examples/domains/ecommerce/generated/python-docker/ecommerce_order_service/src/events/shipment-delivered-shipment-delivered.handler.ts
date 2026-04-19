import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { ShipmentDeliveredEvent } from './shipment-delivered.event';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { NotFoundException } from '@nestjs/common';
import { Order } from '../entities/order.entity';
import { OrderStatus } from '../enums/order-status.enum'

@EventsHandler(ShipmentDeliveredEvent)
export class HandleShipmentDeliveredHandler implements IEventHandler<ShipmentDeliveredEvent> {
  private readonly logger = new Logger(HandleShipmentDeliveredHandler.name);

  constructor(
    @InjectRepository(Order)
    private readonly orderRepository: Repository<Order>,
  ) {}

  async handle(event: ShipmentDeliveredEvent): Promise<void> {
const order = await this.orderRepository.findOneOrFail({ where: { id: event.payload.orderId } });
    await this.dbDataSource.transaction(async (manager: EntityManager) => {
      order.status = OrderStatus.Delivered;
      await this.orderRepository.save(order);
    });
    console.info('order_delivered');;
  }
}

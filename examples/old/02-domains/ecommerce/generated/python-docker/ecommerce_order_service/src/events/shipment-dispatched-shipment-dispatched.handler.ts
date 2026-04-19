import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { ShipmentDispatchedEvent } from './shipment-dispatched.event';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { NotFoundException } from '@nestjs/common';
import { Order } from '../entities/order.entity';
import { OrderStatus } from '../enums/order-status.enum'

@EventsHandler(ShipmentDispatchedEvent)
export class HandleShipmentDispatchedHandler implements IEventHandler<ShipmentDispatchedEvent> {
  private readonly logger = new Logger(HandleShipmentDispatchedHandler.name);

  constructor(
    @InjectRepository(Order)
    private readonly orderRepository: Repository<Order>,
  ) {}

  async handle(event: ShipmentDispatchedEvent): Promise<void> {
const order = await this.orderRepository.findOneOrFail({ where: { id: event.payload.orderId } });
    await this.dbDataSource.transaction(async (manager: EntityManager) => {
      order.shipmentId = event.payload.shipmentId;
      order.status = OrderStatus.Shipped;
      await this.orderRepository.save(order);
    });
    console.info('order_shipped');;
  }
}

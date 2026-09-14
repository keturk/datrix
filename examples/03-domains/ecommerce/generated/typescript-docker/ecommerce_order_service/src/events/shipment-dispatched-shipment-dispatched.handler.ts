import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { ShipmentDispatchedEvent } from './shipment-dispatched.event';
import { EntityManager, EntityRepository } from '@mikro-orm/core';
import { InjectRepository } from '@mikro-orm/nestjs';
import { NotFoundException } from '@nestjs/common';
import { Order } from '../ecommerce_order_service/entities/order_db/order.entity';
import { OrderStatus } from '../enums/order-status.enum';
import { bufferEvents } from '../eventOutbox';

@EventsHandler(ShipmentDispatchedEvent)
export class HandleShipmentDispatchedHandler implements IEventHandler<ShipmentDispatchedEvent> {
  private readonly logger = new Logger(HandleShipmentDispatchedHandler.name);

  constructor(
    @InjectRepository(Order) private readonly orderRepository: EntityRepository<Order>,
    private readonly orderDbEm: EntityManager,
  ) {}

  async handle(event: ShipmentDispatchedEvent): Promise<void> {
const order = await this.orderRepository.findOne({ id: event.payload.orderId });
    if (!order) {
      throw new NotFoundException("Not found");
    }
    await bufferEvents(async () => {
      await this.orderDbEm.transactional(async (manager: EntityManager) => {
      order.shipmentId = event.payload.shipmentId;
      order.status = OrderStatus.Shipped;
      await this.orderRepository.getEntityManager().persistAndFlush(order);
    });
    });
    console.info('order_shipped');
  }
}

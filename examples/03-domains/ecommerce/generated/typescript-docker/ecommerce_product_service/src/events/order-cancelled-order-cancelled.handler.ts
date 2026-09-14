import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { OrderCancelledEvent } from './order-cancelled.event';
import { EntityManager, EntityRepository } from '@mikro-orm/core';
import { InjectRepository } from '@mikro-orm/nestjs';
import { InventoryReservation } from '../ecommerce_product_service/entities/product_db/inventory-reservation.entity';
import { Product } from '../ecommerce_product_service/entities/product_db/product.entity';
import { ReservationStatus } from '../enums/reservation-status.enum';
import { SqlEntityManager } from '@mikro-orm/postgresql';
import { bufferEvents } from '../eventOutbox';
import { producerInstance as mqProducerInstance } from '../mq/producer';

@EventsHandler(OrderCancelledEvent)
export class HandleOrderCancelledHandler implements IEventHandler<OrderCancelledEvent> {
  private readonly logger = new Logger(HandleOrderCancelledHandler.name);

  constructor(
    @InjectRepository(InventoryReservation) private readonly inventoryReservationRepository: EntityRepository<InventoryReservation>,
    @InjectRepository(Product) private readonly productRepository: EntityRepository<Product>,
    private readonly productDbEm: EntityManager,
  ) {}

  async handle(event: OrderCancelledEvent): Promise<void> {
let reservations: InventoryReservation[] = await (this.inventoryReservationRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(InventoryReservation, 'e_inventory_reservation').select('*').where('e_inventory_reservation.reservation_id = ?', [event.payload.reservationId]).andWhere('e_inventory_reservation.status = ?', [ReservationStatus.Reserved]).getResultList();
    // 'transaction(productDb)' wraps operations in a database transaction
    await bufferEvents(async () => {
      await this.productDbEm.transactional(async (manager: EntityManager) => {
      for (const reservation of reservations) {
        let product: Product | null = await this.productRepository.findOne({ id: reservation.product.id });
        if ((product != null)) {
          product.inventory = (product.inventory + reservation.quantity);
          await this.productRepository.getEntityManager().persistAndFlush(product);
        }
        reservation.status = ReservationStatus.Released;
        await this.inventoryReservationRepository.getEntityManager().persistAndFlush(reservation);
      }
    });
    });
    if (mqProducerInstance !== null) {
      await mqProducerInstance.publishInventoryReleased({ reservationId: event.payload.reservationId, reason: `Order cancelled: ${event.payload.reason}` });
    }
    console.info('inventory_released_for_cancelled_order');
  }
}

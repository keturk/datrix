import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { OrderConfirmedEvent } from './order-confirmed.event';
import { EntityManager, EntityRepository } from '@mikro-orm/core';
import { InjectRepository } from '@mikro-orm/nestjs';
import { InventoryReservation } from '../ecommerce_product_service/entities/product_db/inventory-reservation.entity';
import { ReservationStatus } from '../enums/reservation-status.enum';
import { SqlEntityManager } from '@mikro-orm/postgresql';

@EventsHandler(OrderConfirmedEvent)
export class HandleOrderConfirmedHandler implements IEventHandler<OrderConfirmedEvent> {
  private readonly logger = new Logger(HandleOrderConfirmedHandler.name);

  constructor(
    @InjectRepository(InventoryReservation) private readonly inventoryReservationRepository: EntityRepository<InventoryReservation>,
    private readonly productDbEm: EntityManager,
  ) {}

  async handle(event: OrderConfirmedEvent): Promise<void> {
let reservations: InventoryReservation[] = await (this.inventoryReservationRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(InventoryReservation, 'e_inventory_reservation').select('*').where('e_inventory_reservation.reservation_id = ?', [event.payload.reservationId]).andWhere('e_inventory_reservation.status = ?', [ReservationStatus.Reserved]).getResultList();
    for (const reservation of reservations) {
      reservation.status = ReservationStatus.Confirmed;
      await this.inventoryReservationRepository.getEntityManager().persistAndFlush(reservation);
    }
    console.info('inventory_reservation_confirmed');
  }
}

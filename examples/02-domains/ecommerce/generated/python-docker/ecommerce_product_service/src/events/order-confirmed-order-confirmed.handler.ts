import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { OrderConfirmedEvent } from './order-confirmed.event';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { InventoryReservation } from '../entities/inventory-reservation.entity';
import { NotFoundException } from '@nestjs/common';
import { ReservationStatus } from '../enums/reservation-status.enum'

@EventsHandler(OrderConfirmedEvent)
export class HandleOrderConfirmedHandler implements IEventHandler<OrderConfirmedEvent> {
  private readonly logger = new Logger(HandleOrderConfirmedHandler.name);

  constructor(
    @InjectRepository(InventoryReservation)
    private readonly inventoryreservationRepository: Repository<InventoryReservation>,
  ) {}

  async handle(event: OrderConfirmedEvent): Promise<void> {
const reservations: InventoryReservation[] = await this.inventoryReservationRepository.createQueryBuilder('inventoryReservation').where('inventoryReservation.reservationId = :reservationId', { reservationId: event.payload.reservationId }).andWhere('inventoryReservation.status = :status', { status: ReservationStatus.Reserved }).getMany();
    for (const reservation of reservations) {
      reservation.status = ReservationStatus.Confirmed;
      reservation.save();
    }
    console.info('inventory_reservation_confirmed');;
  }
}

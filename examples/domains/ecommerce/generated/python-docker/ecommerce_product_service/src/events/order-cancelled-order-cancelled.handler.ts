import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { OrderCancelledEvent } from './order-cancelled.event';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { InventoryReleasedEvent } from '../events/inventory-released.event';
import { InventoryReservation } from '../entities/inventory-reservation.entity';
import { NotFoundException } from '@nestjs/common';
import { Product } from '../entities/product.entity';
import { ReservationStatus } from '../enums/reservation-status.enum'

@EventsHandler(OrderCancelledEvent)
export class HandleOrderCancelledHandler implements IEventHandler<OrderCancelledEvent> {
  private readonly logger = new Logger(HandleOrderCancelledHandler.name);

  constructor(
    @InjectRepository(InventoryReservation)
    private readonly inventoryreservationRepository: Repository<InventoryReservation>,
    @InjectRepository(Product)
    private readonly productRepository: Repository<Product>,
  ) {}

  async handle(event: OrderCancelledEvent): Promise<void> {
const reservations: InventoryReservation[] = await this.inventoryReservationRepository.createQueryBuilder('inventoryReservation').where('inventoryReservation.reservationId = :reservationId', { reservationId: event.payload.reservationId }).andWhere('inventoryReservation.status = :status', { status: ReservationStatus.Reserved }).getMany();
    await this.dbDataSource.transaction(async (manager: EntityManager) => {
      for (const reservation of reservations) {
        const product: Product | null = await this.productRepository.findOne({ where: { id: reservation.productId } });
        if ((product != null)) {
          product.inventory = (product.inventory + reservation.quantity);
          await this.productRepository.save(product);
        }
        reservation.status = ReservationStatus.Released;
        reservation.save();
      }
    });
    eventEmitter.emit('InventoryReleased', new InventoryReleasedEvent({ reservationId: event.payload.reservationId, reason: `Order cancelled: ${event.payload.reason}` }));
    console.info('inventory_released_for_cancelled_order');;
  }
}

import {
  Entity,
  Column,
  ManyToOne,
  JoinColumn,
  Index,
} from 'typeorm';


import { Product } from './product.entity';
import { ReservationStatus } from '../enums/reservation-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index('idx_inventory_reservations_reservation_id', ['reservationId'])
@Index('idx_inventory_reservations_expires_at', ['expiresAt'])
@Index('idx_inventory_reservations_reservation_id_status', ['reservationId', 'status'])
@Entity('inventory_reservations')
export class InventoryReservation extends BaseEntity {

  @Column({
    type: 'uuid',
  })
  reservationId!: string;

  @Column({
    type: 'int',
  })
  quantity!: number;

  @Column({
    type: 'enum',
    default: ReservationStatus.Reserved,
    enum: ReservationStatus,
  })
  status!: ReservationStatus;

  @Column({
    type: 'timestamp',
  })
  expiresAt!: Date;


  @ManyToOne(() => Product, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'product_id' })
  product!: Product;
  productId!: string;



}

import {
  Entity,
  Property,
  Enum,
  ManyToOne,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { Product } from './product.entity';
import { ReservationStatus } from '../../../enums/reservation-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_inventory_reservations_reservation_id', properties: ['reservationId'] })
@Index({ name: 'idx_inventory_reservations_expires_at', properties: ['expiresAt'] })
@Index({ name: 'idx_inventory_reservations_product_id', properties: ['product'] })
@Index({ name: 'idx_inventory_reservations_reservation_id_status', properties: ['reservationId', 'status'] })
@Entity({ tableName: 'inventory_reservations' })
export class InventoryReservation extends BaseEntity {
  [OptionalProps]?: "createdAt" | "id" | "status" | "updatedAt";


  @Property({ columnType: 'uuid', fieldName: 'reservation_id' })
  reservationId!: string;

  @Property({ columnType: 'int' })
  quantity!: number;

  @Enum({ items: () => ReservationStatus, nativeEnumName: 'reservation_status' })
  status!: ReservationStatus;

  @Property({ columnType: 'timestamptz', fieldName: 'expires_at' })
  expiresAt!: Date;


  @ManyToOne({ entity: () => Product, deleteRule: 'restrict', fieldName: 'product_id' })
  product!: Product;



}

import {
  Entity,
  Property,
  Enum,
  ManyToOne,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { Shipment } from './shipment.entity';
import { ShipmentStatus } from '../../../enums/shipment-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_shipment_events_shipment_id', properties: ['shipment'] })
@Index({ name: 'idx_shipment_events_shipment_id_timestamp', properties: ['shipment', 'timestamp'] })
@Entity({ tableName: 'shipment_events' })
export class ShipmentEvent extends BaseEntity {
  [OptionalProps]?: "createdAt" | "description" | "id" | "updatedAt";


  @Property({ columnType: 'timestamptz' })
  timestamp!: Date;

  @Enum({ items: () => ShipmentStatus, nativeEnumName: 'shipment_status' })
  status!: ShipmentStatus;

  @Property({ columnType: 'varchar' })
  location!: string;

  @Property({ columnType: 'text', nullable: true })
  description!: string | null;


  @ManyToOne({ entity: () => Shipment, inversedBy: 'events', deleteRule: 'restrict', fieldName: 'shipment_id' })
  shipment!: Shipment;



}

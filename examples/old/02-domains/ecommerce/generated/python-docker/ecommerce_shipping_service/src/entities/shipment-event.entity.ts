import {
  Entity,
  Column,
  ManyToOne,
  JoinColumn,
  Index,
} from 'typeorm';


import { Shipment } from './shipment.entity';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index('idx_shipment_events_shipment_id_timestamp', ['shipmentId', 'timestamp'])
@Entity('shipment_events')
export class ShipmentEvent extends BaseEntity {

  @Column({
    type: 'timestamp',
  })
  timestamp!: Date;

  @Column({
    type: 'enum',
    enum: ShipmentStatus,
  })
  status!: ShipmentStatus;

  @Column({
    type: 'varchar',
  })
  location!: string;

  @Column({
    type: 'text',
    nullable: true,
  })
  description?: string | null;


  @ManyToOne(() => Shipment, (shipment) => shipment.events, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'shipment_id' })
  shipment!: Shipment;
  shipmentId!: string;



}

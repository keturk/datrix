import {
  Entity,
  Column,
  ManyToOne,
  JoinColumn,
} from 'typeorm';


import { Shipment } from './shipment.entity';
import { BaseEntity } from './base-entity.entity';

@Entity('shipment_items')
export class ShipmentItem extends BaseEntity {

  @Column({
    type: 'uuid',
  })
  productId!: string;

  @Column({
    type: 'int',
  })
  quantity!: number;


  @ManyToOne(() => Shipment, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'shipment_id' })
  shipment!: Shipment;
  shipmentId!: string;



}

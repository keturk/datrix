import {
  Entity,
  Property,
  ManyToOne,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { Shipment } from './shipment.entity';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_shipment_items_shipment_id', properties: ['shipment'] })
@Entity({ tableName: 'shipment_items' })
export class ShipmentItem extends BaseEntity {
  [OptionalProps]?: "createdAt" | "id" | "updatedAt";


  @Property({ columnType: 'uuid', fieldName: 'product_id' })
  productId!: string;

  @Property({ columnType: 'int' })
  quantity!: number;


  @ManyToOne({ entity: () => Shipment, deleteRule: 'restrict', fieldName: 'shipment_id' })
  shipment!: Shipment;



}

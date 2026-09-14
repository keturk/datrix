import {
  Entity,
  Property,
  ManyToOne,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { Order } from './order.entity';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_order_items_product_id', properties: ['productId'] })
@Index({ name: 'idx_order_items_order_id', properties: ['order'] })
@Entity({ tableName: 'order_items' })
export class OrderItem extends BaseEntity {
  [OptionalProps]?: "createdAt" | "id" | "total" | "updatedAt";


  @Property({ columnType: 'uuid', fieldName: 'product_id' })
  productId!: string;

  @Property({ columnType: 'varchar', fieldName: 'product_name' })
  productName!: string;

  @Property({ columnType: 'int' })
  quantity!: number;

  @Property({ columnType: 'decimal', fieldName: 'unit_price' })
  unitPrice!: number;


  @ManyToOne({ entity: () => Order, inversedBy: 'items', deleteRule: 'restrict', fieldName: 'order_id' })
  order!: Order;

  get total(): number {
    return (this.unitPrice!* this.quantity!);
  }


}

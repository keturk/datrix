import {
  Entity,
  Column,
  ManyToOne,
  JoinColumn,
  Index,
  AfterLoad,
} from 'typeorm';


import { Order } from './order.entity';
import { BaseEntity } from './base-entity.entity';

@Index('idx_order_items_product_id', ['productId'])
@Entity('order_items')
export class OrderItem extends BaseEntity {

  @Column({
    type: 'uuid',
  })
  productId!: string;

  @Column({
    type: 'varchar',
  })
  productName!: string;

  @Column({
    type: 'int',
  })
  quantity!: number;

  @Column({
    type: 'decimal',
  })
  unitPrice!: number;


  @ManyToOne(() => Order, (order) => order.items, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'order_id' })
  order!: Order;
  orderId!: string;

  total!: number;

  @AfterLoad()
  _hydrateComputed(): void {
    this.total = (this.unitPrice!* this.quantity!);
  }


}

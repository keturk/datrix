import {
  Entity,
  Property,
  Enum,
  OneToMany,
  Collection,
  Index,
  OptionalProps,
} from '@mikro-orm/core';

import type { EventEmitter2 } from '@nestjs/event-emitter';
import { Address } from '../../../dto/address.struct'
import { Currency } from '../../../enums/currency.enum'
import { _fieldChanged, _fieldOldValue } from '../../../entity-hook-helpers';

import { OrderItem } from './order-item.entity';
import { OrderStatus } from '../../../enums/order-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_orders_customer_id', properties: ['customerId'] })
@Index({ name: 'idx_orders_order_number', properties: ['orderNumber'] })
@Index({ name: 'idx_orders_customer_id_status', properties: ['customerId', 'status'] })
@Index({ name: 'idx_orders_status_created_at', properties: ['status', 'createdAt'] })
@Entity({ tableName: 'orders' })
export class Order extends BaseEntity {
  [OptionalProps]?: "canCancel" | "cancellationReason" | "createdAt" | "eventEmitter" | "id" | "isCompleted" | "isPendingOrPaymentPending" | "paymentId" | "shipmentId" | "status" | "total" | "updatedAt";

  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('@mikro-orm/core').EntityManager;

  @Property({ columnType: 'uuid', fieldName: 'customer_id' })
  customerId!: string;

  @Property({ columnType: 'varchar', fieldName: 'order_number', unique: true })
  orderNumber!: string;

  @Enum({ items: () => OrderStatus, nativeEnumName: 'order_status' })
  status!: OrderStatus;

  @Property({ columnType: 'decimal' })
  subtotal!: number;

  @Property({ columnType: 'decimal' })
  tax!: number;

  @Property({ columnType: 'decimal', fieldName: 'shipping_cost' })
  shippingCost!: number;

  @Property({ columnType: 'decimal' })
  discount!: number;

  @Property({ columnType: 'jsonb', type: 'json', fieldName: 'shipping_address' })
  shippingAddress!: Address;

  @Property({ columnType: 'jsonb', type: 'json', fieldName: 'billing_address' })
  billingAddress!: Address;

  @Property({ columnType: 'uuid', fieldName: 'inventory_reservation_id' })
  inventoryReservationId!: string;

  @Property({ columnType: 'uuid', fieldName: 'payment_id', nullable: true })
  paymentId!: string | null;

  @Property({ columnType: 'uuid', fieldName: 'shipment_id', nullable: true })
  shipmentId!: string | null;

  @Property({ columnType: 'varchar', fieldName: 'cancellation_reason', nullable: true })
  cancellationReason!: string | null;


  @OneToMany({ entity: () => OrderItem, mappedBy: 'order' })
  items = new Collection<OrderItem>(this);

  get total(): number {
    return (((this.subtotal!+ this.tax!) + this.shippingCost!) + (this.discount!* (-1)));
  }
  get canCancel(): boolean {
    return ((this.status === OrderStatus.Pending) || (this.status === OrderStatus.PaymentPending));
  }
  get isCompleted(): boolean {
    return (this.status === OrderStatus.Delivered);
  }
  get isPendingOrPaymentPending(): boolean {
    return ((this.status === OrderStatus.Pending) || (this.status === OrderStatus.PaymentPending));
  }

  calculateTotals(): void {
    let itemsTotal: number = Number(0);
    for (const item of this.items!) {
      itemsTotal = (itemsTotal + item.total);
    }
    this.subtotal = itemsTotal;
    this.tax = (this.subtotal!* 0.08);
    if ((this.subtotal >= 50.0)) {
      this.shippingCost = Number(0);
    } else {
      this.shippingCost = Number(5.99);
    }
    this.discount = Number(0);
  }


}

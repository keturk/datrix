import {
  Entity,
  Column,
  OneToMany,
  Index,
  BeforeInsert,
  BeforeUpdate,
  BeforeRemove,
  AfterInsert,
  AfterUpdate,
  AfterRemove,
  AfterLoad,
} from 'typeorm';

import type { EventEmitter2 } from '@nestjs/event-emitter';
import { Address } from '../dto/address.struct'
import { OrderCancelledEvent } from '../events/order-cancelled.event';
import { OrderConfirmedEvent } from '../events/order-confirmed.event';
import { OrderCreatedEvent } from '../events/order-created.event';
import { OrderStatusChangedEvent } from '../events/order-status-changed.event';
import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';

import { OrderItem } from './order-item.entity';
import { OrderStatus } from '../enums/order-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index('idx_orders_customer_id', ['customerId'])
@Index('idx_orders_customer_id_status', ['customerId', 'status'])
@Index('idx_orders_status_created_at', ['status', 'createdAt'])
@Entity('orders')
export class Order extends BaseEntity {
  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('typeorm').EntityManager;

  @Column({
    type: 'uuid',
  })
  customerId!: string;

  @Column({
    type: 'varchar',
    unique: true,
  })
  orderNumber!: string;

  @Column({
    type: 'enum',
    default: OrderStatus.Pending,
    enum: OrderStatus,
  })
  status!: OrderStatus;

  @Column({
    type: 'decimal',
  })
  subtotal!: number;

  @Column({
    type: 'decimal',
  })
  tax!: number;

  @Column({
    type: 'decimal',
  })
  shippingCost!: number;

  @Column({
    type: 'decimal',
  })
  discount!: number;

  @Column({
    type: 'jsonb',
  })
  shippingAddress!: Address;

  @Column({
    type: 'jsonb',
  })
  billingAddress!: Address;

  @Column({
    type: 'uuid',
  })
  inventoryReservationId!: string;

  @Column({
    type: 'uuid',
    nullable: true,
  })
  paymentId?: string | null;

  @Column({
    type: 'uuid',
    nullable: true,
  })
  shipmentId?: string | null;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  cancellationReason?: string | null;


  @OneToMany(() => OrderItem, (orderitem) => orderitem.order)
  items!: OrderItem[];

  total!: number;
  canCancel!: boolean;
  isCompleted!: boolean;
  isPendingOrPaymentPending!: boolean;

  @AfterLoad()
  _hydrateComputed(): void {
    this.total = (((this.subtotal!+ this.tax!) + this.shippingCost!) + (this.discount!* (-1)));
    this.canCancel = ((this.status === OrderStatus.Pending) || (this.status === OrderStatus.PaymentPending));
    this.isCompleted = (this.status === OrderStatus.Delivered);
    this.isPendingOrPaymentPending = ((this.status === OrderStatus.Pending) || (this.status === OrderStatus.PaymentPending));
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


  @AfterInsert()
  _hookafterCreate(): void {
    this.eventEmitter.emit('OrderCreated', new OrderCreatedEvent({ orderId: this.id, orderNumber: this.orderNumber, customerId: this.customerId, total: this.total, reservationId: this.inventoryReservationId }));
  }

  @AfterUpdate()
  _hookafterUpdate(): void {
    if (_fieldChanged(this, "status", this.__datrixOldValues!)) {
      this.eventEmitter.emit('OrderStatusChanged', new OrderStatusChangedEvent({ orderId: this.id, oldStatus: _fieldOldValue(this, "status", this.__datrixOldValues!) as OrderStatus, newStatus: this.status }));
      if ((this.status === OrderStatus.Confirmed)) {
        const orderItems: Record<string, unknown>[] = this.items.map((i) => ({productId: i.productId, quantity: i.quantity}));
        const estimatedWeight: number = (this.items.length * 1.0);
        this.eventEmitter.emit('OrderConfirmed', new OrderConfirmedEvent({ orderId: this.id, paymentId: this.paymentId ?? null, reservationId: this.inventoryReservationId, shippingAddress: this.shippingAddress, items: orderItems, estimatedWeight: estimatedWeight }));
      } else if ((this.status === OrderStatus.Cancelled)) {
        this.eventEmitter.emit('OrderCancelled', new OrderCancelledEvent({ orderId: this.id, reason: (this.cancellationReason ?? 'Cancelled'), reservationId: this.inventoryReservationId }));
      }
    }
  }

}

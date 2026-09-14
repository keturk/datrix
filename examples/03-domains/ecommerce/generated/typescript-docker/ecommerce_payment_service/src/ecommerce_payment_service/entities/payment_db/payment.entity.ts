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
import { _fieldChanged, _fieldOldValue } from '../../../entity-hook-helpers';

import { Refund } from './refund.entity';
import { PaymentMethod } from '../../../enums/payment-method.enum';
import { PaymentStatus } from '../../../enums/payment-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_payments_order_id', properties: ['orderId'] })
@Index({ name: 'idx_payments_customer_id', properties: ['customerId'] })
@Index({ name: 'idx_payments_transaction_id', properties: ['transactionId'] })
@Index({ name: 'idx_payments_customer_id_status', properties: ['customerId', 'status'] })
@Entity({ tableName: 'payments' })
export class Payment extends BaseEntity {
  [OptionalProps]?: "canRefund" | "createdAt" | "errorMessage" | "eventEmitter" | "gatewayResponse" | "id" | "isSuccessful" | "processedAt" | "status" | "updatedAt";

  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('@mikro-orm/core').EntityManager;

  @Property({ columnType: 'uuid', fieldName: 'order_id' })
  orderId!: string;

  @Property({ columnType: 'uuid', fieldName: 'customer_id' })
  customerId!: string;

  @Property({ columnType: 'decimal' })
  amount!: number;

  @Enum({ items: () => PaymentMethod, nativeEnumName: 'payment_method' })
  method!: PaymentMethod;

  @Enum({ items: () => PaymentStatus, nativeEnumName: 'payment_status' })
  status!: PaymentStatus;

  @Property({ columnType: 'varchar', fieldName: 'transaction_id', unique: true })
  transactionId!: string;

  @Property({ columnType: 'varchar', fieldName: 'gateway_response', nullable: true })
  gatewayResponse!: string | null;

  @Property({ columnType: 'varchar', fieldName: 'error_message', nullable: true })
  errorMessage!: string | null;

  @Property({ columnType: 'timestamptz', fieldName: 'processed_at', nullable: true })
  processedAt!: Date | null;


  @OneToMany({ entity: () => Refund, mappedBy: 'payment' })
  refunds = new Collection<Refund>(this);

  get isSuccessful(): boolean {
    return (this.status === PaymentStatus.Completed);
  }
  get canRefund(): boolean {
    return (this.status === PaymentStatus.Completed);
  }


}

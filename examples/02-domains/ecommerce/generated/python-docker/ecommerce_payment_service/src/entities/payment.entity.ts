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
import { PaymentFailedEvent } from '../events/payment-failed.event';
import { PaymentProcessedEvent } from '../events/payment-processed.event';
import { PaymentRefundedEvent } from '../events/payment-refunded.event';
import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';

import { Refund } from './refund.entity';
import { PaymentMethod } from '../enums/payment-method.enum';
import { PaymentStatus } from '../enums/payment-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index('idx_payments_order_id', ['orderId'])
@Index('idx_payments_customer_id', ['customerId'])
@Index('idx_payments_customer_id_status', ['customerId', 'status'])
@Entity('payments')
export class Payment extends BaseEntity {
  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('typeorm').EntityManager;

  @Column({
    type: 'uuid',
  })
  orderId!: string;

  @Column({
    type: 'uuid',
  })
  customerId!: string;

  @Column({
    type: 'decimal',
  })
  amount!: number;

  @Column({
    type: 'enum',
    enum: PaymentMethod,
  })
  method!: PaymentMethod;

  @Column({
    type: 'enum',
    default: PaymentStatus.Pending,
    enum: PaymentStatus,
  })
  status!: PaymentStatus;

  @Column({
    type: 'varchar',
    unique: true,
  })
  transactionId!: string;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  gatewayResponse?: string | null;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  errorMessage?: string | null;

  @Column({
    type: 'timestamp',
    nullable: true,
  })
  processedAt?: Date | null;


  @OneToMany(() => Refund, (refund) => refund.payment)
  refunds!: Refund[];

  isSuccessful!: boolean;
  canRefund!: boolean;

  @AfterLoad()
  _hydrateComputed(): void {
    this.isSuccessful = (this.status === PaymentStatus.Completed);
    this.canRefund = (this.status === PaymentStatus.Completed);
  }


  @AfterUpdate()
  _hookafterUpdate(): void {
    if (_fieldChanged(this, "status", this.__datrixOldValues!)) {
      if ((this.status === PaymentStatus.Completed)) {
        this.eventEmitter.emit('PaymentProcessed', new PaymentProcessedEvent({ paymentId: this.id, orderId: this.orderId, amount: this.amount }));
      } else if ((this.status === PaymentStatus.Failed)) {
        this.eventEmitter.emit('PaymentFailed', new PaymentFailedEvent({ paymentId: this.id, orderId: this.orderId, reason: (this.errorMessage ?? 'Payment failed') }));
      } else if ((this.status === PaymentStatus.Refunded)) {
        this.eventEmitter.emit('PaymentRefunded', new PaymentRefundedEvent({ paymentId: this.id, orderId: this.orderId, amount: this.amount }));
      }
    }
  }

}

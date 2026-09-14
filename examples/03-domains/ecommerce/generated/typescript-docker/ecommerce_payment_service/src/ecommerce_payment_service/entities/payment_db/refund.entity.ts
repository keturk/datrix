import {
  Entity,
  Property,
  Enum,
  ManyToOne,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { Payment } from './payment.entity';
import { PaymentStatus } from '../../../enums/payment-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_refunds_payment_id', properties: ['payment'] })
@Entity({ tableName: 'refunds' })
export class Refund extends BaseEntity {
  [OptionalProps]?: "createdAt" | "errorMessage" | "id" | "isSuccessful" | "processedAt" | "refundTransactionId" | "status" | "updatedAt";


  @Property({ columnType: 'decimal' })
  amount!: number;

  @Property({ columnType: 'varchar' })
  reason!: string;

  @Enum({ items: () => PaymentStatus, nativeEnumName: 'payment_status' })
  status!: PaymentStatus;

  @Property({ columnType: 'varchar', fieldName: 'refund_transaction_id', nullable: true })
  refundTransactionId!: string | null;

  @Property({ columnType: 'varchar', fieldName: 'error_message', nullable: true })
  errorMessage!: string | null;

  @Property({ columnType: 'timestamptz', fieldName: 'processed_at', nullable: true })
  processedAt!: Date | null;


  @ManyToOne({ entity: () => Payment, inversedBy: 'refunds', deleteRule: 'restrict', fieldName: 'payment_id' })
  payment!: Payment;

  get isSuccessful(): boolean {
    return (this.status === PaymentStatus.Completed);
  }


}

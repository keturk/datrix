import {
  Entity,
  Column,
  ManyToOne,
  JoinColumn,
  AfterLoad,
} from 'typeorm';


import { Payment } from './payment.entity';
import { PaymentStatus } from '../enums/payment-status.enum';
import { BaseEntity } from './base-entity.entity';

@Entity('refunds')
export class Refund extends BaseEntity {

  @Column({
    type: 'decimal',
  })
  amount!: number;

  @Column({
    type: 'varchar',
  })
  reason!: string;

  @Column({
    type: 'enum',
    default: PaymentStatus.Pending,
    enum: PaymentStatus,
  })
  status!: PaymentStatus;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  refundTransactionId?: string | null;

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


  @ManyToOne(() => Payment, (payment) => payment.refunds, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'payment_id' })
  payment!: Payment;
  paymentId!: string;

  isSuccessful!: boolean;

  @AfterLoad()
  _hydrateComputed(): void {
    this.isSuccessful = (this.status === PaymentStatus.Completed);
  }


}

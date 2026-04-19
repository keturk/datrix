import { PaymentStatus } from '../enums/payment-status.enum';

export class RefundResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  amount!: number;
  reason!: string;
  status!: PaymentStatus;
  refundTransactionId?: string | null;
  errorMessage?: string | null;
  processedAt?: Date | null;
  paymentId!: string;

  isSuccessful!: boolean;
}

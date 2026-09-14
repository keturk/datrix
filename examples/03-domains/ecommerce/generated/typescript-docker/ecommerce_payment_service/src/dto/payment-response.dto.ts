import { PaymentMethod } from '../enums/payment-method.enum';
import { PaymentStatus } from '../enums/payment-status.enum';

export class PaymentResponseDto {
  createdAt!: Date;
  updatedAt!: Date;
  id!: string;
  orderId!: string;
  customerId!: string;
  amount!: number;
  method!: PaymentMethod;
  status!: PaymentStatus;
  transactionId!: string;
  gatewayResponse?: string | null;
  errorMessage?: string | null;
  processedAt?: Date | null;

  isSuccessful!: boolean;
  canRefund!: boolean;
}

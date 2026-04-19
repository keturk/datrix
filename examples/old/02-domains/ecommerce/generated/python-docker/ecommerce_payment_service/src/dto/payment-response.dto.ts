import { PaymentMethod } from '../enums/payment-method.enum';
import { PaymentStatus } from '../enums/payment-status.enum';

export class PaymentResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
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

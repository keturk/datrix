import { OrderStatus } from '../enums/order-status.enum';
import { Address } from './address.struct'

export class OrderResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  customerId!: string;
  orderNumber!: string;
  status!: OrderStatus;
  subtotal!: number;
  tax!: number;
  shippingCost!: number;
  discount!: number;
  shippingAddress!: Address;
  billingAddress!: Address;
  inventoryReservationId!: string;
  paymentId?: string | null;
  shipmentId?: string | null;
  cancellationReason?: string | null;

  total!: number;
  canCancel!: boolean;
  isCompleted!: boolean;
  isPendingOrPaymentPending!: boolean;
}

import { ShippingCarrier } from '../enums/shipping-carrier.enum';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { Address } from './address.struct'

export class ShipmentResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  orderId!: string;
  trackingNumber!: string;
  carrier!: ShippingCarrier;
  status!: ShipmentStatus;
  destination!: Address;
  weight!: number;
  estimatedDelivery?: Date | null;
  actualDelivery?: Date | null;
  failureReason?: string | null;

  isDelivered!: boolean;
  isInProgress!: boolean;
  daysInTransit!: number;
}

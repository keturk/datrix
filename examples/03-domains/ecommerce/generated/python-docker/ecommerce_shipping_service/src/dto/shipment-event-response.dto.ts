import { ShipmentStatus } from '../enums/shipment-status.enum';

export class ShipmentEventResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  timestamp!: Date;
  status!: ShipmentStatus;
  location!: string;
  description?: string | null;
  shipmentId!: string;

}

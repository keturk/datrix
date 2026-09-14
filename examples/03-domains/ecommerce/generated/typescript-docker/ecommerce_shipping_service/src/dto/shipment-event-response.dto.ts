import { ShipmentStatus } from '../enums/shipment-status.enum';

export class ShipmentEventResponseDto {
  createdAt!: Date;
  updatedAt!: Date;
  id!: string;
  timestamp!: Date;
  status!: ShipmentStatus;
  location!: string;
  description?: string | null;
  shipmentId!: string;

}

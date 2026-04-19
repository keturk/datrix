import {
  IsEnum,
  IsOptional,
  IsString,
} from 'class-validator';
import { ShipmentStatus } from '../enums/shipment-status.enum'

export class UpdateShipmentStatusRequest {

  @IsEnum(ShipmentStatus)
  status!: ShipmentStatus;

  @IsOptional()
  @IsString()
  location?: string | null;

  @IsOptional()
  @IsString()
  description?: string | null;


}

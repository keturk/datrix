
import {
  IsDate,
  IsEnum,
  IsNotEmpty,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
} from 'class-validator';
import { Type } from 'class-transformer';
import { ShipmentStatus } from '../enums/shipment-status.enum';

export class CreateShipmentEventDto {

  @IsDate()
  @Type(() => Date)
  timestamp!: Date;

  @IsEnum(ShipmentStatus)
  status!: ShipmentStatus;

  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  location!: string;

  @IsOptional()
  @IsString()
  description?: string | null;

  @IsUUID()
  shipmentId!: string;
}

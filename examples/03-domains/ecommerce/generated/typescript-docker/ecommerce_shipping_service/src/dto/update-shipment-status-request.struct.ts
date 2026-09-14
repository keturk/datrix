import {
  IsEnum,
  IsOptional,
  IsString,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { ShipmentStatus } from '../enums/shipment-status.enum'

export class UpdateShipmentStatusRequest {

  @ApiProperty({ enum: ShipmentStatus, enumName: 'ShipmentStatus' })
  @IsEnum(ShipmentStatus)
  status!: ShipmentStatus;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  location!: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  description!: string | null;


}

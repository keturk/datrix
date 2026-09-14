
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
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ShipmentStatus } from '../enums/shipment-status.enum';

// Event log entity for shipment tracking history
export class CreateShipmentEventDto {

  @ApiProperty()
  @IsDate()
  @Type(() => Date)
  timestamp!: Date;

  @ApiProperty({ enum: ShipmentStatus, enumName: 'ShipmentStatus' })
  @IsEnum(ShipmentStatus)
  status!: ShipmentStatus;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  location!: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  description?: string | null;

  @ApiProperty()
  @IsUUID()
  shipmentId!: string;
}

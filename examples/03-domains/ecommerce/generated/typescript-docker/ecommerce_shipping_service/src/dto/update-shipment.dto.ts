
import {
  IsDate,
  IsDefined,
  IsEnum,
  IsNotEmpty,
  IsNumber,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
  ValidateIf,
  ValidateNested,
} from 'class-validator';
import { ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ShippingCarrier } from '../enums/shipping-carrier.enum';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { Address } from './address.struct'

export class UpdateShipmentDto {

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsUUID()
  orderId?: string;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  trackingNumber?: string;

  @ApiPropertyOptional({ enum: ShippingCarrier, enumName: 'ShippingCarrier' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(ShippingCarrier)
  carrier?: ShippingCarrier;

  @ApiPropertyOptional({ enum: ShipmentStatus, enumName: 'ShipmentStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(ShipmentStatus)
  status?: ShipmentStatus;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  destination?: Address;

  // Decimal(precision, scale) for fixed-point numbers
  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsNumber()
  weight?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  estimatedDelivery?: Date | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  actualDelivery?: Date | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  failureReason?: string | null;
}

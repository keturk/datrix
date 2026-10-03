
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
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ShippingCarrier } from '../enums/shipping-carrier.enum';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { Address } from './address.struct'

export class CreateShipmentDto {

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  orderId!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  trackingNumber!: string;

  @ApiProperty({ enum: ShippingCarrier, enumName: 'ShippingCarrier' })
  @IsDefined()
  @IsEnum(ShippingCarrier)
  carrier!: ShippingCarrier;

  @ApiPropertyOptional({ enum: ShipmentStatus, enumName: 'ShipmentStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(ShipmentStatus)
  status?: ShipmentStatus;

  @ApiProperty()
  @IsDefined()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  destination!: Address;

  // Decimal(precision, scale) for fixed-point numbers
  @ApiProperty()
  @IsDefined()
  @IsNumber()
  weight!: number;

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

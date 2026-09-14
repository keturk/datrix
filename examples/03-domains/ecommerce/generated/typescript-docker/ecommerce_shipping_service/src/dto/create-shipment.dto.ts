
import {
  IsDate,
  IsEnum,
  IsNotEmpty,
  IsNumber,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ShippingCarrier } from '../enums/shipping-carrier.enum';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { Address } from './address.struct'

export class CreateShipmentDto {

  @ApiProperty()
  @IsUUID()
  orderId!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  trackingNumber!: string;

  @ApiProperty({ enum: ShippingCarrier, enumName: 'ShippingCarrier' })
  @IsEnum(ShippingCarrier)
  carrier!: ShippingCarrier;

  @ApiProperty({ enum: ShipmentStatus, enumName: 'ShipmentStatus' })
  @IsEnum(ShipmentStatus)
  status!: ShipmentStatus;

  @ApiProperty()
  @IsObject()
  destination!: Address;

  // Decimal(precision, scale) for fixed-point numbers
  @ApiProperty()
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

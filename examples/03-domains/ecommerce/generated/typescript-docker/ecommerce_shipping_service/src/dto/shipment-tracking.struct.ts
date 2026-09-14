import {
  IsArray,
  IsDate,
  IsEnum,
  IsNotEmpty,
  IsObject,
  IsOptional,
  IsString,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { Address } from '../dto/address.struct'
import { ShipmentEvent } from '../ecommerce_shipping_service/entities/shipping_db/shipment-event.entity'
import { ShipmentStatus } from '../enums/shipment-status.enum'
import { ShippingCarrier } from '../enums/shipping-carrier.enum'

export class ShipmentTracking {

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  trackingNumber!: string;

  @ApiProperty({ enum: ShipmentStatus, enumName: 'ShipmentStatus' })
  @IsEnum(ShipmentStatus)
  status!: ShipmentStatus;

  @ApiProperty({ enum: ShippingCarrier, enumName: 'ShippingCarrier' })
  @IsEnum(ShippingCarrier)
  carrier!: ShippingCarrier;

  @ApiProperty()
  @IsObject()
  destination!: Address;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  estimatedDelivery!: Date | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  actualDelivery!: Date | null;

  // Array of entity references in struct fields
  @ApiProperty()
  @IsArray()
  events!: ShipmentEvent[];


}

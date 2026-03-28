
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
import { Type } from 'class-transformer';
import { ShippingCarrier } from '../enums/shipping-carrier.enum';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { Address } from './address.struct'

export class CreateShipmentDto {

  @IsUUID()
  orderId!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  trackingNumber!: string;

  @IsEnum(ShippingCarrier)
  carrier!: ShippingCarrier;

  @IsEnum(ShipmentStatus)
  status!: ShipmentStatus;

  @IsObject()
  destination!: Address;

  @IsNumber()
  weight!: number;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  estimatedDelivery?: Date | null;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  actualDelivery?: Date | null;

  @IsOptional()
  @IsString()
  failureReason?: string | null;
}

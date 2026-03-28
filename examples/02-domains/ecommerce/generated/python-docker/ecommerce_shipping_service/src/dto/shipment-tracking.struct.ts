import {
  IsArray,
  IsDate,
  IsEnum,
  IsNotEmpty,
  IsObject,
  IsOptional,
  IsString,
} from 'class-validator';
import { Type } from 'class-transformer';
import { Address } from '../dto/address.struct'
import { ShipmentEvent } from '../entities/shipment-event.entity'
import { ShipmentStatus } from '../enums/shipment-status.enum'
import { ShippingCarrier } from '../enums/shipping-carrier.enum'

export class ShipmentTracking {

  @IsString()
  @IsNotEmpty()
  trackingNumber!: string;

  @IsEnum(ShipmentStatus)
  status!: ShipmentStatus;

  @IsEnum(ShippingCarrier)
  carrier!: ShippingCarrier;

  @IsObject()
  destination!: Address;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  estimatedDelivery?: Date | null;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  actualDelivery?: Date | null;

  @IsArray()
  events!: ShipmentEvent[];


}

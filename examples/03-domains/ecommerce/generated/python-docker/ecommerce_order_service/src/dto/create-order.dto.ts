
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
import { OrderStatus } from '../enums/order-status.enum';
import { Address } from './address.struct'

export class CreateOrderDto {

  @IsUUID()
  customerId!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(20)
  orderNumber!: string;

  @IsEnum(OrderStatus)
  status!: OrderStatus;

  @IsNumber({ maxDecimalPlaces: 4 })
  subtotal!: number;

  @IsNumber({ maxDecimalPlaces: 4 })
  tax!: number;

  @IsNumber({ maxDecimalPlaces: 4 })
  shippingCost!: number;

  @IsNumber({ maxDecimalPlaces: 4 })
  discount!: number;

  @IsObject()
  shippingAddress!: Address;

  @IsObject()
  billingAddress!: Address;

  @IsUUID()
  inventoryReservationId!: string;

  @IsOptional()
  @IsUUID()
  paymentId?: string | null;

  @IsOptional()
  @IsUUID()
  shipmentId?: string | null;

  @IsOptional()
  @IsString()
  cancellationReason?: string | null;
}

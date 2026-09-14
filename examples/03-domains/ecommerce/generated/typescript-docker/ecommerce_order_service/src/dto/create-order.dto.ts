
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
import { OrderStatus } from '../enums/order-status.enum';
import { Address } from './address.struct'

// ': audit' enables automatic audit logging for the entity
export class CreateOrderDto {

  @ApiProperty()
  @IsUUID()
  customerId!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(20)
  orderNumber!: string;

  @ApiProperty({ enum: OrderStatus, enumName: 'OrderStatus' })
  @IsEnum(OrderStatus)
  status!: OrderStatus;

  // Money amount fields; currency is passed explicitly at process boundaries
  @ApiProperty()
  @IsNumber({ maxDecimalPlaces: 4 })
  subtotal!: number;

  @ApiProperty()
  @IsNumber({ maxDecimalPlaces: 4 })
  tax!: number;

  @ApiProperty()
  @IsNumber({ maxDecimalPlaces: 4 })
  shippingCost!: number;

  @ApiProperty()
  @IsNumber({ maxDecimalPlaces: 4 })
  discount!: number;

  @ApiProperty()
  @IsObject()
  shippingAddress!: Address;

  @ApiProperty()
  @IsObject()
  billingAddress!: Address;

  @ApiProperty()
  @IsUUID()
  inventoryReservationId!: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsUUID()
  paymentId?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsUUID()
  shipmentId?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  cancellationReason?: string | null;
}

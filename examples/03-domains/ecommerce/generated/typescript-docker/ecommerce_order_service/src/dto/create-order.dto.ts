
import {
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
import { OrderStatus } from '../enums/order-status.enum';
import { Address } from './address.struct'

// ': audit' enables automatic audit logging for the entity
export class CreateOrderDto {

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  customerId!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(20)
  orderNumber!: string;

  @ApiPropertyOptional({ enum: OrderStatus, enumName: 'OrderStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(OrderStatus)
  status?: OrderStatus;

  // Money amount fields; currency is passed explicitly at process boundaries
  @ApiProperty()
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  subtotal!: number;

  @ApiProperty()
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  tax!: number;

  @ApiProperty()
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  shippingCost!: number;

  @ApiProperty()
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  discount!: number;

  @ApiProperty()
  @IsDefined()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  shippingAddress!: Address;

  @ApiProperty()
  @IsDefined()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  billingAddress!: Address;

  @ApiProperty()
  @IsDefined()
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

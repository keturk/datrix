
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
import { ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { OrderStatus } from '../enums/order-status.enum';
import { Address } from './address.struct'

export class UpdateOrderDto {

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsUUID()
  customerId?: string;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(20)
  orderNumber?: string;

  @ApiPropertyOptional({ enum: OrderStatus, enumName: 'OrderStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(OrderStatus)
  status?: OrderStatus;

  // Money amount fields; currency is passed explicitly at process boundaries
  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  subtotal?: number;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  tax?: number;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  shippingCost?: number;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  discount?: number;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  shippingAddress?: Address;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  billingAddress?: Address;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsUUID()
  inventoryReservationId?: string;

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

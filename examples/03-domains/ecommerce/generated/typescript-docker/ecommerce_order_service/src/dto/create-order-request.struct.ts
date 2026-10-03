import {
  IsArray,
  IsObject,
  IsOptional,
  IsString,
  ValidateNested,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { Address } from '../dto/address.struct'
import { OrderLineInput } from '../dto/order-line-input.struct'

export class CreateOrderRequest {

  @ApiProperty()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => OrderLineInput)
  items!: OrderLineInput[];

  @ApiProperty()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  shippingAddress!: Address;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  billingAddress!: Address | null;

  // Idempotency key prevents duplicate order creation on retries
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  idempotencyKey!: string | null;


}

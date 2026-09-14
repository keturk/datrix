import {
  IsArray,
  IsObject,
  IsOptional,
  IsString,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Address } from '../dto/address.struct'
import { OrderLineInput } from '../dto/order-line-input.struct'

export class CreateOrderRequest {

  @ApiProperty()
  @IsArray()
  items!: OrderLineInput[];

  @ApiProperty()
  @IsObject()
  shippingAddress!: Address;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  billingAddress!: Address | null;

  // Idempotency key prevents duplicate order creation on retries
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  idempotencyKey!: string | null;


}

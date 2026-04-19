import {
  IsArray,
  IsObject,
  IsOptional,
  IsString,
} from 'class-validator';
import { Address } from '../dto/address.struct'
import { OrderLineInput } from '../dto/order-line-input.struct'

export class CreateOrderRequest {

  @IsArray()
  items!: OrderLineInput[];

  @IsObject()
  shippingAddress!: Address;

  @IsOptional()
  @IsObject()
  billingAddress?: Address | null;

  @IsOptional()
  @IsString()
  idempotencyKey?: string | null;


}

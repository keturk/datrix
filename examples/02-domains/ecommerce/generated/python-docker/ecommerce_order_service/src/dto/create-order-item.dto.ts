
import {
  IsDate,
  IsInt,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
} from 'class-validator';
import { Type } from 'class-transformer';

export class CreateOrderItemDto {

  @IsUUID()
  productId!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  productName!: string;

  @IsInt()
  quantity!: number;

  @IsNumber({ maxDecimalPlaces: 4 })
  unitPrice!: number;

  @IsUUID()
  orderId!: string;
}


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
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';

export class CreateOrderItemDto {

  @ApiProperty()
  @IsUUID()
  productId!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  productName!: string;

  // 'min(1)' sets a minimum value constraint
  @ApiProperty()
  @IsInt()
  quantity!: number;

  // 'positive' ensures the value is greater than zero
  @ApiProperty()
  @IsNumber({ maxDecimalPlaces: 4 })
  unitPrice!: number;

  @ApiProperty()
  @IsUUID()
  orderId!: string;
}

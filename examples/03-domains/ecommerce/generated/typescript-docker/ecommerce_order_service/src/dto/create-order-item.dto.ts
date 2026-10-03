
import {
  IsDefined,
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
  @IsDefined()
  @IsUUID()
  productId!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  productName!: string;

  // 'min(1)' sets a minimum value constraint
  @ApiProperty()
  @IsDefined()
  @IsInt()
  quantity!: number;

  // 'positive' ensures the value is greater than zero
  @ApiProperty()
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  unitPrice!: number;

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  orderId!: string;
}

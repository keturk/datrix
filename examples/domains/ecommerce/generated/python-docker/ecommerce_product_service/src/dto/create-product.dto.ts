
import {
  IsDate,
  IsEnum,
  IsInt,
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
import { ProductStatus } from '../enums/product-status.enum';

export class CreateProductDto {

  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  slug!: string;

  @IsNumber({ maxDecimalPlaces: 4 })
  price!: number;

  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 4 })
  compareAtPrice?: number | null;

  @IsInt()
  inventory!: number;

  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  name!: string;

  @IsString()
  @IsNotEmpty()
  description!: string;

  @IsEnum(ProductStatus)
  status!: ProductStatus;

  @IsOptional()
  @IsObject()
  productMetadata?: Record<string, unknown> | null;

  @IsObject()
  images!: Record<string, unknown>;

  @IsObject()
  tags!: Record<string, unknown>;

  @IsUUID()
  categoryId!: string;
}

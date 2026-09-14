
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
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ProductStatus } from '../enums/product-status.enum';

// 'with' mixes in multiple traits, adding their fields and methods
export class CreateProductDto {

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @MaxLength(200)
  slug?: string | null;

  // Money is a semantic amount type; currency is modeled explicitly where needed
  @ApiProperty()
  @IsNumber({ maxDecimalPlaces: 4 })
  price!: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 4 })
  compareAtPrice?: number | null;

  // 'min(0)' sets a minimum value constraint
  @ApiProperty()
  @IsInt()
  inventory!: number;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  name!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  description!: string;

  @ApiProperty({ enum: ProductStatus, enumName: 'ProductStatus' })
  @IsEnum(ProductStatus)
  status!: ProductStatus;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  productMetadata?: Record<string, any> | null;

  @ApiProperty()
  @IsObject()
  images!: Record<string, any>;

  @ApiProperty()
  @IsObject()
  tags!: Record<string, any>;

  @ApiProperty()
  @IsUUID()
  categoryId!: string;
}

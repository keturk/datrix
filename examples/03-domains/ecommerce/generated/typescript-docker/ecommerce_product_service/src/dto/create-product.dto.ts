
import {
  IsDefined,
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
  ValidateIf,
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
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  price!: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 4 })
  compareAtPrice?: number | null;

  // 'min(0)' sets a minimum value constraint
  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsInt()
  inventory?: number;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  name!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  description!: string;

  @ApiPropertyOptional({ enum: ProductStatus, enumName: 'ProductStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(ProductStatus)
  status?: ProductStatus;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  productMetadata?: Record<string, any> | null;

  @ApiProperty()
  @IsDefined()
  @IsObject()
  images!: Record<string, any>;

  @ApiProperty()
  @IsDefined()
  @IsObject()
  tags!: Record<string, any>;

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  categoryId!: string;
}

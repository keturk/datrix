
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
import { ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ProductStatus } from '../enums/product-status.enum';

export class UpdateProductDto {

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @MaxLength(200)
  slug?: string | null;

  // Money is a semantic amount type; currency is modeled explicitly where needed
  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsNumber({ maxDecimalPlaces: 4 })
  price?: number;

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

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  name?: string;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  description?: string;

  @ApiPropertyOptional({ enum: ProductStatus, enumName: 'ProductStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(ProductStatus)
  status?: ProductStatus;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  productMetadata?: Record<string, any> | null;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsObject()
  images?: Record<string, any>;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsObject()
  tags?: Record<string, any>;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsUUID()
  categoryId?: string;
}

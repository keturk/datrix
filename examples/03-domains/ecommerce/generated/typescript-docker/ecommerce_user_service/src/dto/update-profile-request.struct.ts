import {
  IsObject,
  IsOptional,
  IsString,
  Matches,
  Max,
  MaxLength,
  Min,
  MinLength,
  ValidateNested,
} from 'class-validator';
import { ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { Address } from '../dto/address.struct'

export class UpdateProfileRequest {

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  firstName!: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  lastName!: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @MinLength(1)
  @MaxLength(20)
  @Matches(/^\+?[1-9]\d{1,14}$/)
  phoneNumber!: string | null;

  // Address struct imported from the common module
  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  shippingAddress!: Address | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  billingAddress!: Address | null;


}

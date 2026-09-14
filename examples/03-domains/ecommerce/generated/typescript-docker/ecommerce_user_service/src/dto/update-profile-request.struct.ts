import {
  IsObject,
  IsOptional,
  IsString,
  Matches,
  Max,
  MaxLength,
  Min,
  MinLength,
} from 'class-validator';
import { ApiPropertyOptional } from '@nestjs/swagger';
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
  shippingAddress!: Address | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  billingAddress!: Address | null;


}

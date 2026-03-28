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
import { Address } from '../dto/address.struct'

export class UpdateProfileRequest {

  @IsOptional()
  @IsString()
  firstName?: string | null;

  @IsOptional()
  @IsString()
  lastName?: string | null;

  @IsOptional()
  @MinLength(1)
  @MaxLength(20)
  @Matches(/^\+?[1-9]\d{1,14}$/)
  phoneNumber?: string | null;

  @IsOptional()
  @IsObject()
  shippingAddress?: Address | null;

  @IsOptional()
  @IsObject()
  billingAddress?: Address | null;


}

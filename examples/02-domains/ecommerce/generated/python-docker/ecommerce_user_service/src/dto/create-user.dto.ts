
import {
  IsDate,
  IsEmail,
  IsEnum,
  IsNotEmpty,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
  Matches,
  Max,
  MaxLength,
  Min,
  MinLength,
} from 'class-validator';
import { Type } from 'class-transformer';
import { UserRole } from '../enums/user-role.enum';
import { UserStatus } from '../enums/user-status.enum';
import { Address } from './address.struct'

export class CreateUserDto {

  @IsEmail()
  email!: string;

  @IsString()
  passwordHash!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  firstName!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  lastName!: string;

  @IsOptional()
  @MinLength(1)
  @MaxLength(20)
  @Matches(/^\+?[1-9]\d{1,14}$/)
  phoneNumber?: string | null;

  @IsEnum(UserRole)
  role!: UserRole;

  @IsEnum(UserStatus)
  status!: UserStatus;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  lastLoginAt?: Date | null;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  emailVerifiedAt?: Date | null;

  @IsOptional()
  @IsString()
  emailVerificationToken?: string | null;

  @IsOptional()
  @IsString()
  passwordResetToken?: string | null;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  passwordResetExpiry?: Date | null;

  @IsOptional()
  @IsObject()
  shippingAddress?: Address | null;

  @IsOptional()
  @IsObject()
  billingAddress?: Address | null;
}

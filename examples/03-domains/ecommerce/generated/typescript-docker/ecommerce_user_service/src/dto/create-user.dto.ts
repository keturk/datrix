
import {
  IsDate,
  IsDefined,
  IsEmail,
  IsEnum,
  IsNotEmpty,
  IsObject,
  IsOptional,
  IsString,
  Matches,
  Max,
  MaxLength,
  Min,
  MinLength,
  ValidateIf,
  ValidateNested,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { UserRole } from '../enums/user-role.enum';
import { UserStatus } from '../enums/user-status.enum';
import { Address } from './address.struct'

export class CreateUserDto {

  @ApiProperty()
  @IsDefined()
  @IsEmail()
  email!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  passwordHash!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  firstName!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  lastName!: string;

  @ApiPropertyOptional()
  @IsOptional()
  @MinLength(1)
  @MaxLength(20)
  @Matches(/^\+?[1-9]\d{1,14}$/)
  phoneNumber?: string | null;

  @ApiPropertyOptional({ enum: UserRole, enumName: 'UserRole' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(UserRole)
  role?: UserRole;

  @ApiPropertyOptional({ enum: UserStatus, enumName: 'UserStatus' })
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsEnum(UserStatus)
  status?: UserStatus;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  lastLoginAt?: Date | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  emailVerifiedAt?: Date | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  emailVerificationToken?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  passwordResetToken?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  passwordResetExpiry?: Date | null;

  // Embedded struct fields for complex nested data
  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  shippingAddress?: Address | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  billingAddress?: Address | null;
}

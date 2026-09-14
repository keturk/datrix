
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
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { UserRole } from '../enums/user-role.enum';
import { UserStatus } from '../enums/user-status.enum';
import { Address } from './address.struct'

export class CreateUserDto {

  @ApiProperty()
  @IsEmail()
  email!: string;

  @ApiProperty()
  @IsString()
  passwordHash!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  firstName!: string;

  @ApiProperty()
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

  @ApiProperty({ enum: UserRole, enumName: 'UserRole' })
  @IsEnum(UserRole)
  role!: UserRole;

  @ApiProperty({ enum: UserStatus, enumName: 'UserStatus' })
  @IsEnum(UserStatus)
  status!: UserStatus;

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
  shippingAddress?: Address | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  billingAddress?: Address | null;
}

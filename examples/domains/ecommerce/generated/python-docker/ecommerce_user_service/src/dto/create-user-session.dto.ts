
import {
  IsDate,
  IsIP,
  IsNotEmpty,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
} from 'class-validator';
import { Type } from 'class-transformer';

export class CreateUserSessionDto {

  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  token!: string;

  @IsOptional()
  @IsString()
  @MaxLength(500)
  deviceName?: string | null;

  @IsOptional()
  @IsIP()
  ipAddress?: string | null;

  @IsOptional()
  @IsString()
  @MaxLength(255)
  userAgent?: string | null;

  @IsDate()
  @Type(() => Date)
  expiresAt!: Date;

  @IsOptional()
  @IsDate()
  @Type(() => Date)
  lastActivityAt?: Date | null;

  @IsUUID()
  userId!: string;
}

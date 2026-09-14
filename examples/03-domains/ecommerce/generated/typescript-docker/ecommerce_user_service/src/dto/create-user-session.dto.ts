
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
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';

export class CreateUserSessionDto {

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  token!: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @MaxLength(500)
  deviceName?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsIP()
  ipAddress?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  @MaxLength(255)
  userAgent?: string | null;

  @ApiProperty()
  @IsDate()
  @Type(() => Date)
  expiresAt!: Date;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  lastActivityAt?: Date | null;

  @ApiProperty()
  @IsUUID()
  userId!: string;
}

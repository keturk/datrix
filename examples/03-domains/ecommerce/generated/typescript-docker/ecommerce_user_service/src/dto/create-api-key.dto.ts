
import {
  IsArray,
  IsBoolean,
  IsDate,
  IsDefined,
  IsInt,
  IsNotEmpty,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
  ValidateIf,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';

// Issued API keys. Only the SHA-256 hash of a key is stored;
// keyPrefix is display-only and never used to verify a key.
export class CreateApiKeyDto {

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(64)
  keyHash!: string;

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  ownerId!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(12)
  keyPrefix!: string;

  @ApiProperty()
  @IsDefined()
  @IsArray()
  @IsString({ each: true })
  scopes!: string[];

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsBoolean()
  isActive?: boolean;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  expiresAt?: Date | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsDate()
  @Type(() => Date)
  lastUsedAt?: Date | null;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsInt()
  rateLimit?: number;
}

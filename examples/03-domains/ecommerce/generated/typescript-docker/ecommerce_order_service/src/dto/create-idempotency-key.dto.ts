
import {
  IsDate,
  IsNotEmpty,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';

// Entity for idempotency key deduplication
export class CreateIdempotencyKeyDto {

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  key!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  operation!: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsUUID()
  resourceId?: string | null;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  response?: Record<string, any> | null;

  @ApiProperty()
  @IsDate()
  @Type(() => Date)
  expiresAt!: Date;
}

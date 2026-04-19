
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
import { Type } from 'class-transformer';

export class CreateIdempotencyKeyDto {

  @IsString()
  @IsNotEmpty()
  @MaxLength(100)
  key!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  operation!: string;

  @IsOptional()
  @IsUUID()
  resourceId?: string | null;

  @IsOptional()
  @IsObject()
  response?: Record<string, unknown> | null;

  @IsDate()
  @Type(() => Date)
  expiresAt!: Date;
}

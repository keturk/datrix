
import {
  IsBoolean,
  IsDefined,
  IsNotEmpty,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
  ValidateIf,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';

export class CreateUserPreferencesDto {

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(10)
  language?: string;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  timezone?: string;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsBoolean()
  emailNotifications?: boolean;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsDefined()
  @IsBoolean()
  smsNotifications?: boolean;

  // JSON type for schemaless data
  @ApiProperty()
  @IsDefined()
  @IsObject()
  preferences!: Record<string, any>;

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  userId!: string;
}

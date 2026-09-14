
import {
  IsBoolean,
  IsDate,
  IsNotEmpty,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';

export class CreateUserPreferencesDto {

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(10)
  language!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  timezone!: string;

  @ApiProperty()
  @IsBoolean()
  emailNotifications!: boolean;

  @ApiProperty()
  @IsBoolean()
  smsNotifications!: boolean;

  // JSON type for schemaless data
  @ApiProperty()
  @IsObject()
  preferences!: Record<string, any>;

  @ApiProperty()
  @IsUUID()
  userId!: string;
}

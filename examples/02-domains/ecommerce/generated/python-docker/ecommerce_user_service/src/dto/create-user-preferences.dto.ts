
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
import { Type } from 'class-transformer';

export class CreateUserPreferencesDto {

  @IsString()
  @IsNotEmpty()
  @MaxLength(10)
  language!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(50)
  timezone!: string;

  @IsBoolean()
  emailNotifications!: boolean;

  @IsBoolean()
  smsNotifications!: boolean;

  @IsObject()
  preferences!: Record<string, unknown>;

  @IsUUID()
  userId!: string;
}


import {
  IsDefined,
  IsEnum,
  IsNotEmpty,
  IsOptional,
  IsString,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { DevicePlatform } from '../enums/device-platform.enum';

export class CreateDeviceRegistrationDto {

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  subject!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  token!: string;

  @ApiProperty({ enum: DevicePlatform, enumName: 'DevicePlatform' })
  @IsDefined()
  @IsEnum(DevicePlatform)
  platform!: DevicePlatform;
}

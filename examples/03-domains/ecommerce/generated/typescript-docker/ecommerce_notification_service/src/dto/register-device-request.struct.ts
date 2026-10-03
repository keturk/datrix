import {
  IsEnum,
  IsNotEmpty,
  IsString,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { DevicePlatform } from '../enums/device-platform.enum'

export class RegisterDeviceRequest {

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  token!: string;

  @ApiProperty({ enum: DevicePlatform, enumName: 'DevicePlatform' })
  @IsEnum(DevicePlatform)
  platform!: DevicePlatform;


}

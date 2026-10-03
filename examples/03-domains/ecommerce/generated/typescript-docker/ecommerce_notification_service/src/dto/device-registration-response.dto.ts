import { DevicePlatform } from '../enums/device-platform.enum';

export class DeviceRegistrationResponseDto {
  id!: string;
  subject!: string;
  token!: string;
  platform!: DevicePlatform;
  createdAt!: Date;
  updatedAt!: Date;

}

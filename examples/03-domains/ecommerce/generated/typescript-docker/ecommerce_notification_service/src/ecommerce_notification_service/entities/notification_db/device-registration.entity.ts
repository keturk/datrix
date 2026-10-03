import {
  Entity,
  Property,
  PrimaryKey,
  Enum,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { DevicePlatform } from '../../../enums/device-platform.enum';

@Index({ name: 'idx_device_registrations_subject', properties: ['subject'] })
@Entity({ tableName: 'device_registrations' })
export class DeviceRegistration {
  [OptionalProps]?: "createdAt" | "id" | "updatedAt";


  @PrimaryKey({ columnType: 'uuid', defaultRaw: 'gen_random_uuid()' })
  id!: string;

  @Property({ columnType: 'varchar' })
  subject!: string;

  @Property({ columnType: 'varchar' })
  token!: string;

  @Enum({ items: () => DevicePlatform, nativeEnumName: 'device_platform' })
  platform!: DevicePlatform;

  @Property({ columnType: 'timestamptz', fieldName: 'created_at', defaultRaw: 'CURRENT_TIMESTAMP' })
  createdAt!: Date;

  @Property({ columnType: 'timestamptz', fieldName: 'updated_at' })
  updatedAt!: Date;





}

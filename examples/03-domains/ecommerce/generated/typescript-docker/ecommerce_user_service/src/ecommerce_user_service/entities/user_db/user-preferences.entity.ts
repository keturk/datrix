import {
  Entity,
  Property,
  OneToOne,
  OptionalProps,
} from '@mikro-orm/core';


import { User } from './user.entity';
import { BaseEntity } from './base-entity.entity';

@Entity({ tableName: 'user_preferences' })
export class UserPreferences extends BaseEntity {
  [OptionalProps]?: "createdAt" | "emailNotifications" | "id" | "language" | "smsNotifications" | "timezone" | "updatedAt";


  @Property({ columnType: 'varchar', default: 'en' })
  language!: string;

  @Property({ columnType: 'varchar', default: 'UTC' })
  timezone!: string;

  @Property({ columnType: 'boolean', fieldName: 'email_notifications', default: true })
  emailNotifications!: boolean;

  @Property({ columnType: 'boolean', fieldName: 'sms_notifications', default: false })
  smsNotifications!: boolean;

  @Property({ columnType: 'jsonb', type: 'json' })
  preferences!: Record<string, any>;


  @OneToOne({ entity: () => User, inversedBy: 'preferences', owner: true, fieldName: 'user_id', deleteRule: 'restrict' })
  user!: User;



}

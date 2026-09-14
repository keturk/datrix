import {
  Entity,
  Property,
  ManyToOne,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { User } from './user.entity';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_user_sessions_token', properties: ['token'] })
@Index({ name: 'idx_user_sessions_user_id', properties: ['user'] })
@Index({ name: 'idx_user_sessions_user_id_expires_at', properties: ['user', 'expiresAt'] })
@Entity({ tableName: 'user_sessions' })
export class UserSession extends BaseEntity {
  [OptionalProps]?: "createdAt" | "deviceName" | "id" | "ipAddress" | "isActive" | "isExpired" | "lastActivityAt" | "updatedAt" | "userAgent";


  @Property({ columnType: 'varchar', unique: true })
  token!: string;

  @Property({ columnType: 'varchar', fieldName: 'device_name', nullable: true })
  deviceName!: string | null;

  @Property({ columnType: 'varchar', fieldName: 'ip_address', nullable: true })
  ipAddress!: string | null;

  @Property({ columnType: 'varchar', fieldName: 'user_agent', nullable: true })
  userAgent!: string | null;

  @Property({ columnType: 'timestamptz', fieldName: 'expires_at' })
  expiresAt!: Date;

  @Property({ columnType: 'timestamptz', fieldName: 'last_activity_at', nullable: true })
  lastActivityAt!: Date | null;


  @ManyToOne({ entity: () => User, inversedBy: 'sessions', deleteRule: 'restrict', fieldName: 'user_id' })
  user!: User;

  get isExpired(): boolean {
    return (new Date() > this.expiresAt!);
  }
  get isActive(): boolean {
    return ((!this.isExpired) && (this.lastActivityAt != null));
  }


}

import {
  Entity,
  Property,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_api_keys_owner_id', properties: ['ownerId'] })
@Entity({ tableName: 'api_keys' })
export class ApiKey extends BaseEntity {
  [OptionalProps]?: "createdAt" | "expiresAt" | "id" | "isActive" | "lastUsedAt" | "rateLimit" | "updatedAt";


  @Property({ columnType: 'varchar', fieldName: 'key_hash', unique: true })
  keyHash!: string;

  @Property({ columnType: 'uuid', fieldName: 'owner_id' })
  ownerId!: string;

  @Property({ columnType: 'varchar', fieldName: 'key_prefix' })
  keyPrefix!: string;

  @Property({ columnType: 'jsonb', type: 'json' })
  scopes!: string[];

  @Property({ columnType: 'boolean', fieldName: 'is_active', default: true })
  isActive: boolean = true;

  @Property({ columnType: 'timestamptz', fieldName: 'expires_at', nullable: true })
  expiresAt!: Date | null;

  @Property({ columnType: 'timestamptz', fieldName: 'last_used_at', nullable: true })
  lastUsedAt!: Date | null;

  @Property({ columnType: 'int', fieldName: 'rate_limit', default: 100 })
  rateLimit: number = 100;





}

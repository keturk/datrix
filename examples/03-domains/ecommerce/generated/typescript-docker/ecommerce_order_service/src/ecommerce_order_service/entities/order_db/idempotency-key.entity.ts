import {
  Entity,
  Property,
  Index,
  OptionalProps,
} from '@mikro-orm/core';


import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_idempotency_keys_operation', properties: ['operation'] })
@Index({ name: 'idx_idempotency_keys_expires_at', properties: ['expiresAt'] })
@Entity({ tableName: 'idempotency_keys' })
export class IdempotencyKey extends BaseEntity {
  [OptionalProps]?: "createdAt" | "id" | "resourceId" | "response" | "updatedAt";


  @Property({ columnType: 'varchar', unique: true })
  key!: string;

  @Property({ columnType: 'varchar' })
  operation!: string;

  @Property({ columnType: 'uuid', fieldName: 'resource_id', nullable: true })
  resourceId!: string | null;

  @Property({ columnType: 'jsonb', type: 'json', nullable: true })
  response!: Record<string, any> | null;

  @Property({ columnType: 'timestamptz', fieldName: 'expires_at' })
  expiresAt!: Date;





}

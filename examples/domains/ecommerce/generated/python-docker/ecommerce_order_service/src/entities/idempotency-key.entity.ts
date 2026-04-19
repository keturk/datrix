import {
  Entity,
  Column,
  Index,
} from 'typeorm';


import { BaseEntity } from './base-entity.entity';

@Index('idx_idempotency_keys_operation', ['operation'])
@Index('idx_idempotency_keys_expires_at', ['expiresAt'])
@Entity('idempotency_keys')
export class IdempotencyKey extends BaseEntity {

  @Column({
    type: 'varchar',
    unique: true,
  })
  key!: string;

  @Column({
    type: 'varchar',
  })
  operation!: string;

  @Column({
    type: 'uuid',
    nullable: true,
  })
  resourceId?: string | null;

  @Column({
    type: 'jsonb',
    nullable: true,
  })
  response?: Record<string, unknown> | null;

  @Column({
    type: 'timestamp',
  })
  expiresAt!: Date;





}

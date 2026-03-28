import {
  Entity,
  Column,
  ManyToOne,
  JoinColumn,
} from 'typeorm';


import { User } from './user.entity';
import { BaseEntity } from './base-entity.entity';

@Entity('user_preferenceses')
export class UserPreferences extends BaseEntity {

  @Column({
    type: 'varchar',
    default: 'en',
  })
  language!: string;

  @Column({
    type: 'varchar',
    default: 'UTC',
  })
  timezone!: string;

  @Column({
    type: 'boolean',
    default: true,
  })
  emailNotifications!: boolean;

  @Column({
    type: 'boolean',
    default: false,
  })
  smsNotifications!: boolean;

  @Column({
    type: 'jsonb',
  })
  preferences!: Record<string, unknown>;


  @ManyToOne(() => User, (user) => user.preferences, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'user_id' })
  user!: User;
  userId!: string;



}

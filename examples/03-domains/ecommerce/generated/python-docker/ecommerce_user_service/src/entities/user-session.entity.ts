import {
  Entity,
  Column,
  ManyToOne,
  JoinColumn,
  Index,
  AfterLoad,
} from 'typeorm';


import { User } from './user.entity';
import { BaseEntity } from './base-entity.entity';

@Index('idx_user_sessions_user_id_expires_at', ['userId', 'expiresAt'])
@Entity('user_sessions')
export class UserSession extends BaseEntity {

  @Column({
    type: 'varchar',
    unique: true,
  })
  token!: string;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  deviceName?: string | null;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  ipAddress?: string | null;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  userAgent?: string | null;

  @Column({
    type: 'timestamp',
  })
  expiresAt!: Date;

  @Column({
    type: 'timestamp',
    nullable: true,
  })
  lastActivityAt?: Date | null;


  @ManyToOne(() => User, (user) => user.sessions, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'user_id' })
  user!: User;
  userId!: string;

  isExpired!: boolean;
  isActive!: boolean;

  @AfterLoad()
  _hydrateComputed(): void {
    this.isExpired = (new Date() > this.expiresAt!);
    this.isActive = ((!this.isExpired!) && (this.lastActivityAt != null));
  }


}

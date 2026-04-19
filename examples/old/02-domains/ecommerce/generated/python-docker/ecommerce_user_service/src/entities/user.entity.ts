import {
  Entity,
  Column,
  OneToMany,
  OneToOne,
  JoinColumn,
  Index,
  BeforeInsert,
  BeforeUpdate,
  BeforeRemove,
  AfterInsert,
  AfterUpdate,
  AfterRemove,
  AfterLoad,
} from 'typeorm';

import type { EventEmitter2 } from '@nestjs/event-emitter';
import { Address } from '../dto/address.struct'
import { UserRegisteredEvent } from '../events/user-registered.event';
import { UserStatusChangedEvent } from '../events/user-status-changed.event';
import { UserVerifiedEvent } from '../events/user-verified.event';
import { _emailSend, _emailSendTemplate, _emailSendBulk } from '../ecommerce_user_service/_emailHelpers';
import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';

import { UserSession } from './user-session.entity';
import { UserPreferences } from './user-preferences.entity';
import { UserRole } from '../enums/user-role.enum';
import { UserStatus } from '../enums/user-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index('idx_users_status_role', ['status', 'role'])
@Entity('users')
export class User extends BaseEntity {
  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('typeorm').EntityManager;

  @Column({
    type: 'varchar',
    unique: true,
  })
  email!: string;

  @Column({
    type: 'varchar',
  })
  passwordHash!: string;

  @Column({
    type: 'varchar',
  })
  firstName!: string;

  @Column({
    type: 'varchar',
  })
  lastName!: string;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  phoneNumber?: string | null;

  @Column({
    type: 'enum',
    default: UserRole.Customer,
    enum: UserRole,
  })
  role!: UserRole;

  @Column({
    type: 'enum',
    default: UserStatus.Pending,
    enum: UserStatus,
  })
  status!: UserStatus;

  @Column({
    type: 'timestamp',
    nullable: true,
  })
  lastLoginAt?: Date | null;

  @Column({
    type: 'timestamp',
    nullable: true,
  })
  emailVerifiedAt?: Date | null;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  emailVerificationToken?: string | null;

  @Column({
    type: 'varchar',
    nullable: true,
  })
  passwordResetToken?: string | null;

  @Column({
    type: 'timestamp',
    nullable: true,
  })
  passwordResetExpiry?: Date | null;

  @Column({
    type: 'jsonb',
    nullable: true,
  })
  shippingAddress?: Address | null;

  @Column({
    type: 'jsonb',
    nullable: true,
  })
  billingAddress?: Address | null;


  @OneToMany(() => UserSession, (usersession) => usersession.user)
  sessions!: UserSession[];
  @OneToOne(() => UserPreferences, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'user_preferences_id' })
  preferences!: UserPreferences;
  preferencesId!: string;

  fullName!: string;
  isActive!: boolean;
  isVerified!: boolean;
  canLogin!: boolean;

  @AfterLoad()
  _hydrateComputed(): void {
    this.fullName = `${this.firstName} ${this.lastName}`;
    this.isActive = (this.status === UserStatus.Active);
    this.isVerified = (this.emailVerifiedAt != null);
    this.canLogin = (this.isActive && this.isVerified!);
  }


  @BeforeUpdate()
  _hookbeforeUpdate(): void {
    this.updatedAt = new Date();
  }

  @AfterInsert()
  async _hookafterCreate(): Promise<void> {
    this.eventEmitter.emit('UserRegistered', new UserRegisteredEvent({ userId: this.id, email: this.email, fullName: this.fullName }));
    await _emailSend({to: this.email, subject: 'Verify your email', template: 'emailVerification', data: {token: this.emailVerificationToken, fullName: this.fullName}});
  }

  @AfterUpdate()
  _hookafterUpdate(): void {
    if (_fieldChanged(this, "status", this.__datrixOldValues!)) {
      this.eventEmitter.emit('UserStatusChanged', new UserStatusChangedEvent({ userId: this.id, oldStatus: _fieldOldValue(this, "status", this.__datrixOldValues!) as UserStatus, newStatus: this.status }));
      if (((this.status === UserStatus.Active) && this.isVerified!)) {
        this.eventEmitter.emit('UserVerified', new UserVerifiedEvent({ userId: this.id, email: this.email }));
      }
    }
  }

}

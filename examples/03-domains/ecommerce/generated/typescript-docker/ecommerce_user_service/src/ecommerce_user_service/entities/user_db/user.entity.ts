import {
  Entity,
  Property,
  Enum,
  OneToMany,
  OneToOne,
  Collection,
  Index,
  OptionalProps,
} from '@mikro-orm/core';

import type { EventEmitter2 } from '@nestjs/event-emitter';
import { Address } from '../../../dto/address.struct'
import { _fieldChanged, _fieldOldValue } from '../../../entity-hook-helpers';

import { UserSession } from './user-session.entity';
import { UserPreferences } from './user-preferences.entity';
import { UserRole } from '../../../enums/user-role.enum';
import { UserStatus } from '../../../enums/user-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_users_email', properties: ['email'] })
@Index({ name: 'idx_users_status_role', properties: ['status', 'role'] })
@Entity({ tableName: 'users' })
export class User extends BaseEntity {
  [OptionalProps]?: "billingAddress" | "canLogin" | "createdAt" | "emailVerificationToken" | "emailVerifiedAt" | "eventEmitter" | "fullName" | "id" | "isActive" | "isVerified" | "lastLoginAt" | "passwordResetExpiry" | "passwordResetToken" | "phoneNumber" | "preferences" | "role" | "shippingAddress" | "status" | "updatedAt";

  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('@mikro-orm/core').EntityManager;

  @Property({ columnType: 'varchar', unique: true })
  email!: string;

  @Property({ columnType: 'varchar', fieldName: 'password_hash' })
  passwordHash!: string;

  @Property({ columnType: 'varchar', fieldName: 'first_name' })
  firstName!: string;

  @Property({ columnType: 'varchar', fieldName: 'last_name' })
  lastName!: string;

  @Property({ columnType: 'varchar', fieldName: 'phone_number', nullable: true })
  phoneNumber!: string | null;

  @Enum({ items: () => UserRole, nativeEnumName: 'user_role' })
  role!: UserRole;

  @Enum({ items: () => UserStatus, nativeEnumName: 'user_status' })
  status!: UserStatus;

  @Property({ columnType: 'timestamptz', fieldName: 'last_login_at', nullable: true })
  lastLoginAt!: Date | null;

  @Property({ columnType: 'timestamptz', fieldName: 'email_verified_at', nullable: true })
  emailVerifiedAt!: Date | null;

  @Property({ columnType: 'varchar', fieldName: 'email_verification_token', nullable: true })
  emailVerificationToken!: string | null;

  @Property({ columnType: 'varchar', fieldName: 'password_reset_token', nullable: true })
  passwordResetToken!: string | null;

  @Property({ columnType: 'timestamptz', fieldName: 'password_reset_expiry', nullable: true })
  passwordResetExpiry!: Date | null;

  @Property({ columnType: 'jsonb', type: 'json', fieldName: 'shipping_address', nullable: true })
  shippingAddress!: Address | null;

  @Property({ columnType: 'jsonb', type: 'json', fieldName: 'billing_address', nullable: true })
  billingAddress!: Address | null;


  @OneToMany({ entity: () => UserSession, mappedBy: 'user' })
  sessions = new Collection<UserSession>(this);
  @OneToOne({ entity: () => UserPreferences, mappedBy: 'user' })
  preferences!: UserPreferences;

  get fullName(): string {
    return `${this.firstName} ${this.lastName}`;
  }
  get isActive(): boolean {
    return (this.status === UserStatus.Active);
  }
  get isVerified(): boolean {
    return (this.emailVerifiedAt != null);
  }
  get canLogin(): boolean {
    return (this.isActive && this.isVerified!);
  }


}

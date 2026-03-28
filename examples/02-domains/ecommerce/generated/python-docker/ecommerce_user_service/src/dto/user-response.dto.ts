import { UserRole } from '../enums/user-role.enum';
import { UserStatus } from '../enums/user-status.enum';
import { Address } from './address.struct'

export class UserResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  email!: string;
  firstName!: string;
  lastName!: string;
  phoneNumber?: string | null;
  role!: UserRole;
  status!: UserStatus;
  lastLoginAt?: Date | null;
  emailVerifiedAt?: Date | null;
  emailVerificationToken?: string | null;
  passwordResetToken?: string | null;
  passwordResetExpiry?: Date | null;
  shippingAddress?: Address | null;
  billingAddress?: Address | null;

  fullName!: string;
  isActive!: boolean;
  isVerified!: boolean;
  canLogin!: boolean;
}

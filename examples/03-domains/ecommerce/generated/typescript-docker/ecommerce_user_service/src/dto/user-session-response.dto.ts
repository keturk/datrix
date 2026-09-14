
export class UserSessionResponseDto {
  createdAt!: Date;
  updatedAt!: Date;
  id!: string;
  token!: string;
  deviceName?: string | null;
  ipAddress?: string | null;
  userAgent?: string | null;
  expiresAt!: Date;
  lastActivityAt?: Date | null;
  userId!: string;

  isExpired!: boolean;
  isActive!: boolean;
}

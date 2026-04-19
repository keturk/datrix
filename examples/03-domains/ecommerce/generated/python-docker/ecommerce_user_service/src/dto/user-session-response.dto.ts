
export class UserSessionResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
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


export class ApiKeyResponseDto {
  createdAt!: Date;
  updatedAt!: Date;
  id!: string;
  keyHash!: string;
  ownerId!: string;
  keyPrefix!: string;
  scopes!: string[];
  isActive!: boolean;
  expiresAt?: Date | null;
  lastUsedAt?: Date | null;
  rateLimit!: number;

}

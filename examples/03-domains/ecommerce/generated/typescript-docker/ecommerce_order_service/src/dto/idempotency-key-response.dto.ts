
export class IdempotencyKeyResponseDto {
  createdAt!: Date;
  updatedAt!: Date;
  id!: string;
  key!: string;
  operation!: string;
  resourceId?: string | null;
  response?: Record<string, any> | null;
  expiresAt!: Date;

}

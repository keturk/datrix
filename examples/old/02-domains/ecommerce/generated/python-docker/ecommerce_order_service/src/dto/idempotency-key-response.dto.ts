
export class IdempotencyKeyResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  key!: string;
  operation!: string;
  resourceId?: string | null;
  response?: Record<string, unknown> | null;
  expiresAt!: Date;

}

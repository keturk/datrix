import type { EntityManager } from '@mikro-orm/core';
import { User } from '../ecommerce_user_service/entities/user_db/user.entity';

export async function userDbUserBeforeUpdate(
  target: User,
  db: EntityManager,
  oldValues?: Record<string, unknown>,
): Promise<void> {
  target.updatedAt = new Date();
}
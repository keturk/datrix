import type { EntityManager } from '@mikro-orm/core';
import { User } from '../ecommerce_user_service/entities/user_db/user.entity';

import { UserStatus } from '../enums/user-status.enum'
import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';
import { producerInstance as mqProducerInstance } from '../mq/producer';

export async function userDbUserAfterUpdate(
  target: User,
  db: EntityManager,
  oldValues?: Record<string, unknown>,
): Promise<void> {
  if (_fieldChanged(target, "status", oldValues)) {
    if (mqProducerInstance !== null) {
    await mqProducerInstance.publishUserStatusChanged({ userId: target.id, oldStatus: _fieldOldValue(target, "status", oldValues) as UserStatus, newStatus: target.status });
  }
    if (((target.status === UserStatus.Active) && target.isVerified)) {
      if (mqProducerInstance !== null) {
    await mqProducerInstance.publishUserVerified({ userId: target.id, email: target.email });
  }
    }
  }
}
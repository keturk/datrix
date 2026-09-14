import type { EntityManager } from '@mikro-orm/core';
import { User } from '../ecommerce_user_service/entities/user_db/user.entity';

import { _emailSend, _emailSendTemplate, _emailSendBulk } from '../ecommerce_user_service/_emailHelpers';
import { producerInstance as mqProducerInstance } from '../mq/producer';

export async function userDbUserAfterCreate(
  target: User,
  db: EntityManager,
  oldValues?: Record<string, unknown>,
): Promise<void> {
  if (mqProducerInstance !== null) {
    await mqProducerInstance.publishUserRegistered({ userId: target.id, email: target.email, fullName: target.fullName });
  }
  await _emailSend({to: target.email, subject: 'Verify your email', template: 'emailVerification', data: {token: target.emailVerificationToken, fullName: target.fullName}});
}
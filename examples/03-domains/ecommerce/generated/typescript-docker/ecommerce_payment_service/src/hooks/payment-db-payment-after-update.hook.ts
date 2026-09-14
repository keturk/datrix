import type { EntityManager } from '@mikro-orm/core';
import { Payment } from '../ecommerce_payment_service/entities/payment_db/payment.entity';

import { PaymentStatus } from '../enums/payment-status.enum'
import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';
import { producerInstance as mqProducerInstance } from '../mq/producer';

export async function paymentDbPaymentAfterUpdate(
  target: Payment,
  db: EntityManager,
  oldValues?: Record<string, unknown>,
): Promise<void> {
  if (_fieldChanged(target, "status", oldValues)) {
    if ((target.status === PaymentStatus.Completed)) {
      if (mqProducerInstance !== null) {
    await mqProducerInstance.publishPaymentProcessed({ paymentId: target.id, orderId: target.orderId, amount: target.amount });
  }
    } else if ((target.status === PaymentStatus.Failed)) {
      if (mqProducerInstance !== null) {
    await mqProducerInstance.publishPaymentFailed({ paymentId: target.id, orderId: target.orderId, reason: (target.errorMessage ?? 'Payment failed') });
  }
    } else if ((target.status === PaymentStatus.Refunded)) {
      if (mqProducerInstance !== null) {
    await mqProducerInstance.publishPaymentRefunded({ paymentId: target.id, orderId: target.orderId, amount: target.amount });
  }
    }
  }
}
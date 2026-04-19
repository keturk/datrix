import { Injectable, Logger } from '@nestjs/common';
import { PaymentFailedEvent } from './payment-failed.event';
import type { PaymentFailedPayload } from '../mq/schemas';
import { PaymentProcessedEvent } from './payment-processed.event';
import type { PaymentProcessedPayload } from '../mq/schemas';
import { PaymentRefundedEvent } from './payment-refunded.event';
import type { PaymentRefundedPayload } from '../mq/schemas';

@Injectable()
export class PaymentServiceEventPublisher {
  private readonly logger = new Logger(PaymentServiceEventPublisher.name);

  constructor(private readonly eventBus: { publish: (event: unknown) => Promise<void> }) {}

  async publishPaymentFailed(payload: Partial<PaymentFailedPayload>): Promise<void> {
    this.logger.log(`Publishing PaymentFailed`);
    await this.eventBus.publish(new PaymentFailedEvent(payload as PaymentFailedPayload));
  }
  async publishPaymentProcessed(payload: Partial<PaymentProcessedPayload>): Promise<void> {
    this.logger.log(`Publishing PaymentProcessed`);
    await this.eventBus.publish(new PaymentProcessedEvent(payload as PaymentProcessedPayload));
  }
  async publishPaymentRefunded(payload: Partial<PaymentRefundedPayload>): Promise<void> {
    this.logger.log(`Publishing PaymentRefunded`);
    await this.eventBus.publish(new PaymentRefundedEvent(payload as PaymentRefundedPayload));
  }
}

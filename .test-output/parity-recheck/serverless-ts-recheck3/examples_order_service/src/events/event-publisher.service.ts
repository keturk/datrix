import { Injectable, Logger } from '@nestjs/common';
import { OrderCancelledEvent } from './order-cancelled.event';
import type { OrderCancelledPayload } from '../mq/schemas';
import { OrderPlacedEvent } from './order-placed.event';
import type { OrderPlacedPayload } from '../mq/schemas';

@Injectable()
export class OrderServiceEventPublisher {
  private readonly logger = new Logger(OrderServiceEventPublisher.name);

  constructor(private readonly eventBus: { publish: (event: unknown) => Promise<void> }) {}

  async publishOrderCancelled(payload: Partial<OrderCancelledPayload>): Promise<void> {
    this.logger.log(`Publishing OrderCancelled`);
    await this.eventBus.publish(new OrderCancelledEvent(payload as OrderCancelledPayload));
  }
  async publishOrderPlaced(payload: Partial<OrderPlacedPayload>): Promise<void> {
    this.logger.log(`Publishing OrderPlaced`);
    await this.eventBus.publish(new OrderPlacedEvent(payload as OrderPlacedPayload));
  }
}

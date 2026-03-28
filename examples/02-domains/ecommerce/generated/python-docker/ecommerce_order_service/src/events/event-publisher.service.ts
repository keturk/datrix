import { Injectable, Logger } from '@nestjs/common';
import { OrderCancelledEvent } from './order-cancelled.event';
import type { OrderCancelledPayload } from '../mq/schemas';
import { OrderConfirmedEvent } from './order-confirmed.event';
import type { OrderConfirmedPayload } from '../mq/schemas';
import { OrderCreatedEvent } from './order-created.event';
import type { OrderCreatedPayload } from '../mq/schemas';
import { OrderStatusChangedEvent } from './order-status-changed.event';
import type { OrderStatusChangedPayload } from '../mq/schemas';

@Injectable()
export class OrderServiceEventPublisher {
  private readonly logger = new Logger(OrderServiceEventPublisher.name);

  constructor(private readonly eventBus: { publish: (event: unknown) => Promise<void> }) {}

  async publishOrderCancelled(payload: Partial<OrderCancelledPayload>): Promise<void> {
    this.logger.log(`Publishing OrderCancelled`);
    await this.eventBus.publish(new OrderCancelledEvent(payload as OrderCancelledPayload));
  }
  async publishOrderConfirmed(payload: Partial<OrderConfirmedPayload>): Promise<void> {
    this.logger.log(`Publishing OrderConfirmed`);
    await this.eventBus.publish(new OrderConfirmedEvent(payload as OrderConfirmedPayload));
  }
  async publishOrderCreated(payload: Partial<OrderCreatedPayload>): Promise<void> {
    this.logger.log(`Publishing OrderCreated`);
    await this.eventBus.publish(new OrderCreatedEvent(payload as OrderCreatedPayload));
  }
  async publishOrderStatusChanged(payload: Partial<OrderStatusChangedPayload>): Promise<void> {
    this.logger.log(`Publishing OrderStatusChanged`);
    await this.eventBus.publish(new OrderStatusChangedEvent(payload as OrderStatusChangedPayload));
  }
}

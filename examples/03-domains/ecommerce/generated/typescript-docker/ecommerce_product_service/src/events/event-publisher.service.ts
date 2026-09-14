import { Injectable, Logger } from '@nestjs/common';
import { InventoryReleasedEvent } from './inventory-released.event';
import type { InventoryReleasedPayload } from '../mq/schemas';
import { InventoryReservedEvent } from './inventory-reserved.event';
import type { InventoryReservedPayload } from '../mq/schemas';
import { InventoryUpdatedEvent } from './inventory-updated.event';
import type { InventoryUpdatedPayload } from '../mq/schemas';
import { ProductCreatedEvent } from './product-created.event';
import type { ProductCreatedPayload } from '../mq/schemas';

@Injectable()
export class ProductServiceEventPublisher {
  private readonly logger = new Logger(ProductServiceEventPublisher.name);

  constructor(private readonly eventBus: { publish: (event: unknown) => Promise<void> }) {}

  async publishInventoryReleased(payload: Partial<InventoryReleasedPayload>): Promise<void> {
    this.logger.log(`Publishing InventoryReleased`);
    await this.eventBus.publish(new InventoryReleasedEvent(payload as InventoryReleasedPayload));
  }
  async publishInventoryReserved(payload: Partial<InventoryReservedPayload>): Promise<void> {
    this.logger.log(`Publishing InventoryReserved`);
    await this.eventBus.publish(new InventoryReservedEvent(payload as InventoryReservedPayload));
  }
  async publishInventoryUpdated(payload: Partial<InventoryUpdatedPayload>): Promise<void> {
    this.logger.log(`Publishing InventoryUpdated`);
    await this.eventBus.publish(new InventoryUpdatedEvent(payload as InventoryUpdatedPayload));
  }
  async publishProductCreated(payload: Partial<ProductCreatedPayload>): Promise<void> {
    this.logger.log(`Publishing ProductCreated`);
    await this.eventBus.publish(new ProductCreatedEvent(payload as ProductCreatedPayload));
  }
}

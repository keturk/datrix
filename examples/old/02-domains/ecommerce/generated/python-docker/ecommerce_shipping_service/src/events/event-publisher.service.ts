import { Injectable, Logger } from '@nestjs/common';
import { ShipmentCreatedEvent } from './shipment-created.event';
import type { ShipmentCreatedPayload } from '../mq/schemas';
import { ShipmentDeliveredEvent } from './shipment-delivered.event';
import type { ShipmentDeliveredPayload } from '../mq/schemas';
import { ShipmentDispatchedEvent } from './shipment-dispatched.event';
import type { ShipmentDispatchedPayload } from '../mq/schemas';
import { ShipmentFailedEvent } from './shipment-failed.event';
import type { ShipmentFailedPayload } from '../mq/schemas';

@Injectable()
export class ShippingServiceEventPublisher {
  private readonly logger = new Logger(ShippingServiceEventPublisher.name);

  constructor(private readonly eventBus: { publish: (event: unknown) => Promise<void> }) {}

  async publishShipmentCreated(payload: Partial<ShipmentCreatedPayload>): Promise<void> {
    this.logger.log(`Publishing ShipmentCreated`);
    await this.eventBus.publish(new ShipmentCreatedEvent(payload as ShipmentCreatedPayload));
  }
  async publishShipmentDelivered(payload: Partial<ShipmentDeliveredPayload>): Promise<void> {
    this.logger.log(`Publishing ShipmentDelivered`);
    await this.eventBus.publish(new ShipmentDeliveredEvent(payload as ShipmentDeliveredPayload));
  }
  async publishShipmentDispatched(payload: Partial<ShipmentDispatchedPayload>): Promise<void> {
    this.logger.log(`Publishing ShipmentDispatched`);
    await this.eventBus.publish(new ShipmentDispatchedEvent(payload as ShipmentDispatchedPayload));
  }
  async publishShipmentFailed(payload: Partial<ShipmentFailedPayload>): Promise<void> {
    this.logger.log(`Publishing ShipmentFailed`);
    await this.eventBus.publish(new ShipmentFailedEvent(payload as ShipmentFailedPayload));
  }
}

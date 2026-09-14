import type { EntityManager } from '@mikro-orm/core';
import { Shipment } from '../ecommerce_shipping_service/entities/shipping_db/shipment.entity';

import { ShipmentEvent } from '../ecommerce_shipping_service/entities/shipping_db/shipment-event.entity';
import { ShipmentStatus } from '../enums/shipment-status.enum'
import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';
import { producerInstance as mqProducerInstance } from '../mq/producer';

export async function shippingDbShipmentAfterUpdate(
  target: Shipment,
  db: EntityManager,
  oldValues?: Record<string, unknown>,
): Promise<void> {
  if (_fieldChanged(target, "status", oldValues)) {
    const entity = this.__datrixEntityManager!.getRepository(ShipmentEvent).create({ shipment: target, timestamp: new Date(), status: target.status, location: 'System', description: `Status updated to ${target.status}` } as never);
    await this.__datrixEntityManager!.getRepository(ShipmentEvent).getEntityManager().persistAndFlush(entity);
    if ((target.status === ShipmentStatus.InTransit)) {
      if (mqProducerInstance !== null) {
    await mqProducerInstance.publishShipmentDispatched({ shipmentId: target.id, orderId: target.orderId, trackingNumber: target.trackingNumber });
  }
    } else if ((target.status === ShipmentStatus.Delivered)) {
      if (mqProducerInstance !== null) {
    await mqProducerInstance.publishShipmentDelivered({ shipmentId: target.id, orderId: target.orderId, deliveredAt: (target.actualDelivery ?? new Date()) });
  }
    } else if ((target.status === ShipmentStatus.Failed)) {
      if (mqProducerInstance !== null) {
    await mqProducerInstance.publishShipmentFailed({ shipmentId: target.id, orderId: target.orderId, reason: (target.failureReason ?? 'Delivery failed') });
  }
    }
  }
}
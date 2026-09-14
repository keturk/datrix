import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { OrderConfirmedEvent } from './order-confirmed.event';
import { EntityRepository } from '@mikro-orm/core';
import { InjectRepository } from '@mikro-orm/nestjs';
import { Shipment } from '../ecommerce_shipping_service/entities/shipping_db/shipment.entity';
import { ShipmentEvent } from '../ecommerce_shipping_service/entities/shipping_db/shipment-event.entity';
import { ShipmentItem } from '../ecommerce_shipping_service/entities/shipping_db/shipment-item.entity';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { ShippingCarrier } from '../enums/shipping-carrier.enum';
import { _getRedis } from '../ecommerce_shipping_service/_cacheHelpers';
import { calculateEstimatedDelivery, generateTrackingNumber, selectCarrier } from '../functions';
import { format } from 'date-fns';
import { producerInstance as mqProducerInstance } from '../mq/producer';

@EventsHandler(OrderConfirmedEvent)
export class HandleOrderConfirmedHandler implements IEventHandler<OrderConfirmedEvent> {
  private readonly logger = new Logger(HandleOrderConfirmedHandler.name);

  constructor(
    @InjectRepository(Shipment) private readonly shipmentRepository: EntityRepository<Shipment>,
    @InjectRepository(ShipmentEvent) private readonly shipmentEventRepository: EntityRepository<ShipmentEvent>,
    @InjectRepository(ShipmentItem) private readonly shipmentItemRepository: EntityRepository<ShipmentItem>,
  ) {}

  async handle(event: OrderConfirmedEvent): Promise<void> {
let carrier: ShippingCarrier = await selectCarrier(event.payload.shippingAddress, event.payload.estimatedWeight);
    let estimatedDelivery: Date = await calculateEstimatedDelivery(carrier, event.payload.shippingAddress);
    const shipment = this.shipmentRepository.create({ orderId: event.payload.orderId, trackingNumber: await generateTrackingNumber(), carrier: carrier, destination: event.payload.shippingAddress, weight: event.payload.estimatedWeight, status: ShipmentStatus.Pending, estimatedDelivery: estimatedDelivery } as never);
    await this.shipmentRepository.getEntityManager().persistAndFlush(shipment);
    for (const item of event.payload.items) {
      const entity = this.shipmentItemRepository.create({ shipment: shipment, productId: item.productId, quantity: item.quantity } as never);
      await this.shipmentItemRepository.getEntityManager().persistAndFlush(entity);
    }
    const entity = this.shipmentEventRepository.create({ shipment: shipment, timestamp: new Date(), status: ShipmentStatus.Pending, location: 'Warehouse', description: 'Shipment created, awaiting pickup' } as never);
    await this.shipmentEventRepository.getEntityManager().persistAndFlush(entity);
    if (mqProducerInstance !== null) {
      await mqProducerInstance.publishShipmentCreated({ shipmentId: shipment.id, orderId: event.payload.orderId });
    }
    // Increment daily shipment counter
    (await Promise.all([_getRedis().incr((String("shipments:daily:") + ':' + String(format(new Date(), 'yyyy-MM-dd')))), _getRedis().expire((String("shipments:daily:") + ':' + String(format(new Date(), 'yyyy-MM-dd'))), 86400)]))[0];
    console.info('shipment_created_from_order_confirmation');
  }
}

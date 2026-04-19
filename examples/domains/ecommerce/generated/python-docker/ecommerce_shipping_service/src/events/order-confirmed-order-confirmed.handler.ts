import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { OrderConfirmedEvent } from './order-confirmed.event';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { NotFoundException } from '@nestjs/common';
import { Shipment } from '../entities/shipment.entity';
import { ShipmentCreatedEvent } from '../events/shipment-created.event';
import { ShipmentEvent } from '../entities/shipment-event.entity';
import { ShipmentItem } from '../entities/shipment-item.entity';
import { ShipmentStatus } from '../enums/shipment-status.enum'
import { ShippingCarrier } from '../enums/shipping-carrier.enum'
import { _getRedis } from '../ecommerce_shipping_service/_cacheHelpers';
import { calculateEstimatedDelivery } from 'ecommerce-shipping-service/functions';
import { format } from 'date-fns';
import { selectCarrier } from 'ecommerce-shipping-service/functions';

@EventsHandler(OrderConfirmedEvent)
export class HandleOrderConfirmedHandler implements IEventHandler<OrderConfirmedEvent> {
  private readonly logger = new Logger(HandleOrderConfirmedHandler.name);

  constructor(
    @InjectRepository(Shipment)
    private readonly shipmentRepository: Repository<Shipment>,
    @InjectRepository(ShipmentEvent)
    private readonly shipmenteventRepository: Repository<ShipmentEvent>,
    @InjectRepository(ShipmentItem)
    private readonly shipmentitemRepository: Repository<ShipmentItem>,
  ) {}

  async handle(event: OrderConfirmedEvent): Promise<void> {
const carrier: ShippingCarrier = selectCarrier(event.payload.shippingAddress, event.payload.estimatedWeight);
    const estimatedDelivery: Date = calculateEstimatedDelivery(carrier, event.payload.shippingAddress);
    const shipment = this.shipmentRepository.create({orderId: event.payload.orderId, trackingNumber: generateTrackingNumber(), carrier: carrier, destination: event.payload.shippingAddress, weight: event.payload.estimatedWeight, status: ShipmentStatus.Pending, estimatedDelivery: estimatedDelivery});
    await this.shipmentRepository.save(shipment);
    for (const item of event.payload.items) {
      const entity = this.shipmentItemRepository.create({shipment: shipment, productId: item.productId, quantity: item.quantity});
      await this.shipmentItemRepository.save(entity);
    }
    const entity = this.shipmentEventRepository.create({shipment: shipment, timestamp: new Date(), status: ShipmentStatus.Pending, location: 'Warehouse', description: 'Shipment created, awaiting pickup'});
    await this.shipmentEventRepository.save(entity);
    eventEmitter.emit('ShipmentCreated', new ShipmentCreatedEvent({ shipmentId: shipment.id, orderId: event.payload.orderId }));
    await _getRedis().incr(format(new Date(), 'YYYY-MM-DD'));;
    console.info('shipment_created_from_order_confirmation');;
  }
}

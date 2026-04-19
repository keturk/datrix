import {
  Controller,
  Get,
  Post,
  Put,
  Param,
  DefaultValuePipe,
  ParseIntPipe,
  Body,
  HttpCode,
  HttpStatus,
  ParseUUIDPipe,
  UseGuards,
} from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { AuthGuard } from '../auth/auth.guard';
import { Public } from '../auth/public.decorator';
import { InternalGuard } from '../auth/internal.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { ShipmentService } from '../services/shipment.service';
import { ShipmentEventService } from '../services/shipment_event.service';
import { AddTrackingEventRequest } from '../dto/add-tracking-event-request.struct';
import { CreateShipmentRequest } from '../dto/create-shipment-request.struct';
import { FedExWebhookRequest } from '../dto/fed-ex-webhook-request.struct';
import { GetShippingRatesRequest } from '../dto/get-shipping-rates-request.struct';
import { NotFoundException } from '@nestjs/common';
import { ShipmentCreatedEvent } from '../events/shipment-created.event';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { ShipmentTracking } from '../dto/shipment-tracking.struct';
import { ShippingCarrier } from '../enums/shipping-carrier.enum';
import { ShippingRateResponse } from '../dto/shipping-rate-response.struct';
import { UpdateShipmentStatusRequest } from '../dto/update-shipment-status-request.struct';
import { _getRedis } from '../ecommerce_shipping_service/_cacheHelpers';
import { calculateEstimatedDelivery } from 'ecommerce-shipping-service/functions';
import { format } from 'date-fns';
import { getEstimatedDays } from 'ecommerce-shipping-service/functions';
import { selectCarrier } from 'ecommerce-shipping-service/functions';
import { Shipment } from '../entities/shipment.entity';
import { ShipmentEvent } from '../entities/shipment-event.entity';
import { ShipmentItem } from '../entities/shipment-item.entity';

@UseGuards(AuthGuard)
@Controller('api/v1/shipments')
export class ShippingAPIController {
  constructor(
    private readonly shipmentService: ShipmentService,
    private readonly shipmentEventService: ShipmentEventService,
    @InjectRepository(Shipment) private readonly shipmentRepository: Repository<Shipment>,
    @InjectRepository(ShipmentEvent) private readonly shipmentEventRepository: Repository<ShipmentEvent>,
    @InjectRepository(ShipmentItem) private readonly shipmentItemRepository: Repository<ShipmentItem>,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  @UseGuards(InternalGuard)
  @Post('')
  @HttpCode(HttpStatus.CREATED)
  async postEndpoint(
    @Body() request: CreateShipmentRequest,
  ): Promise<Shipment> {
    const carrier: ShippingCarrier = selectCarrier(request.destination, request.weight);
    const estimatedDelivery: Date = calculateEstimatedDelivery(carrier, request.destination);
    const shipment = this.shipmentRepository.create({orderId: request.orderId, trackingNumber: generateTrackingNumber(), carrier: carrier, destination: request.destination, weight: request.weight, status: ShipmentStatus.Pending, estimatedDelivery: estimatedDelivery});
    await this.shipmentRepository.save(shipment);
    for (const item of request.items) {
      const entity = this.shipmentItemRepository.create({shipment: shipment, productId: item.productId, quantity: item.quantity});
      await this.shipmentItemRepository.save(entity);
    }
    const entity = this.shipmentEventRepository.create({shipment: shipment, timestamp: new Date(), status: ShipmentStatus.Pending, location: 'Warehouse', description: 'Shipment created, awaiting pickup'});
    await this.shipmentEventRepository.save(entity);
    this.eventEmitter.emit('ShipmentCreated', new ShipmentCreatedEvent({ shipmentId: shipment.id, orderId: request.orderId }));
    await _getRedis().incr(format(new Date(), 'YYYY-MM-DD'));;
    console.info('shipment_created');;
    return shipment;
  }

  @Public()
  @Post('rates')
  @HttpCode(HttpStatus.CREATED)
  async postRates(
    @Body() request: GetShippingRatesRequest,
  ): Promise<ShippingRateResponse[]> {
    const rates: ShippingRateResponse[] = [];
    rates.push({carrier: ShippingCarrier.FedEx, rate: calculateRate(ShippingCarrier.FedEx, request.destination, request.weight), estimatedDays: getEstimatedDays(ShippingCarrier.FedEx, request.destination)});
    rates.push({carrier: ShippingCarrier.Ups, rate: calculateRate(ShippingCarrier.Ups, request.destination, request.weight), estimatedDays: getEstimatedDays(ShippingCarrier.Ups, request.destination)});
    rates.push({carrier: ShippingCarrier.Usps, rate: calculateRate(ShippingCarrier.Usps, request.destination, request.weight), estimatedDays: getEstimatedDays(ShippingCarrier.Usps, request.destination)});
    return rates;
  }

  @Public()
  @Post('webhook/fedex')
  @HttpCode(HttpStatus.CREATED)
  async postWebhookFedex(
    @Body() request: FedExWebhookRequest,
  ): Promise<void> {
    const trackingNumber: string = request.payload.trackingNumber;
    const eventType: string = request.payload.eventType;
    const location: string = (request.payload.location ?? 'Unknown');
    const shipment: Shipment | null = await this.shipmentRepository.createQueryBuilder('shipment').where('shipment.trackingNumber = :trackingNumber', { trackingNumber: trackingNumber }).getOne();
    if ((shipment == null)) {
      console.warn('webhook_received_for_unknown_tracking_number');;
      return;
    }
    const newStatus: ShipmentStatus = mapFedExStatus(eventType);
    const entity = this.shipmentEventRepository.create({shipment: shipment, timestamp: new Date(), status: newStatus, location: location, description: request.payload.description});
    await this.shipmentEventRepository.save(entity);
    if ((shipment.status !== newStatus)) {
      shipment.status = newStatus;
      if ((newStatus === ShipmentStatus.Delivered)) {
        shipment.actualDelivery = new Date();
      }
      await this.shipmentRepository.save(shipment);
    }
    await _getRedis().del(`shipmentCache:${trackingNumber}`);;
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Post(':id/events')
  @HttpCode(HttpStatus.CREATED)
  async postEvents(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() request: AddTrackingEventRequest,
  ): Promise<ShipmentEvent> {
    const shipment = await this.shipmentRepository.findOneOrFail({ where: { id: id } });
    const event = this.shipmentEventRepository.create({shipment: shipment, timestamp: new Date(), status: request.status, location: request.location, description: request.description});
    await this.shipmentEventRepository.save(event);
    if ((shipment.status !== request.status)) {
      shipment.status = request.status;
      if ((request.status === ShipmentStatus.Delivered)) {
        shipment.actualDelivery = new Date();
      }
      await this.shipmentRepository.save(shipment);
    }
    await _getRedis().del(`shipmentCache:${shipment.trackingNumber}`);;
    return event;
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Put(':id/status')
  async putStatus(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() request: UpdateShipmentStatusRequest,
  ): Promise<Shipment> {
    const shipment = await this.shipmentRepository.findOneOrFail({ where: { id: id } });
    const oldStatus: ShipmentStatus = shipment.status;
    shipment.status = request.status;
    if ((request.status === ShipmentStatus.Delivered)) {
      shipment.actualDelivery = new Date();
    }
    await this.shipmentRepository.save(shipment);
    const entity = this.shipmentEventRepository.create({shipment: shipment, timestamp: new Date(), status: request.status, location: (request.location ?? 'Unknown'), description: (request.description ?? `Status updated to ${request.status}`)});
    await this.shipmentEventRepository.save(entity);
    await _getRedis().del(`shipmentCache:${shipment.trackingNumber}`);;
    console.info('shipment_status_updated');;
    return shipment;
  }

  @Get('order/:orderId')
  async getOrder(
    @Param('orderId', ParseUUIDPipe) orderId: string,
  ): Promise<Shipment> {
    return this.shipmentService.findOne(orderId);
  }

  @Get('shipments/:id')
  async getShipment(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Shipment> {
    return this.shipmentService.findOne(id);
  }

  @Public()
  @Get('track/:trackingNumber')
  async getTrack(
    @Param('trackingNumber') trackingNumber: string,
  ): Promise<ShipmentTracking> {
    const cached: Record<string, unknown> | null = (JSON.parse(await _getRedis().get(`shipmentCache:${trackingNumber}`) ?? 'null') as unknown);
    const shipment = await this.shipmentRepository.createQueryBuilder('shipment').where('shipment.trackingNumber = :trackingNumber', { trackingNumber: trackingNumber }).getOneOrFail();
    const events: ShipmentEvent[] = await this.shipmentEventRepository.createQueryBuilder('shipmentEvent').where('shipmentEvent.shipmentId = :shipmentId', { shipmentId: shipment.id }).orderBy('shipmentEvent.timestamp', 'ASC').getMany();
    await _getRedis().set(`shipmentCache:${trackingNumber}`, JSON.stringify({trackingNumber: trackingNumber, status: shipment.status, estimatedDelivery: shipment.estimatedDelivery}));;
    return {trackingNumber: trackingNumber, status: shipment.status, carrier: shipment.carrier, destination: shipment.destination, estimatedDelivery: shipment.estimatedDelivery, actualDelivery: shipment.actualDelivery, events: events};
  }

  @Get('shipments/:id/shipment_events')
  async listShipmentEvents(
    @Param('id', ParseUUIDPipe) id: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('take', new DefaultValuePipe(20), ParseIntPipe) take: number,
  ): Promise<ShipmentEvent[]> {
    await this.shipmentService.findOne(id);
    return this.shipmentEventService.getByShipment(id, skip, take);
  }

}

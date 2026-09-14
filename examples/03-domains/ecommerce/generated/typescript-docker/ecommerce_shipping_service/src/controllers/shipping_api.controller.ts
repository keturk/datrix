import {
  Controller,
  Get,
  Patch,
  Post,
  Param,
  Query,
  DefaultValuePipe,
  ParseIntPipe,
  Body,
  HttpCode,
  HttpStatus,
  ParseUUIDPipe,
  UseGuards,
} from '@nestjs/common';
import { AuthGuard } from '../auth/auth.guard';
import { Public } from '../auth/public.decorator';
import { InternalGuard } from '../auth/internal.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { WebhookVerify, WebhookVerifyGuard } from '../auth/webhook-verify.guard';
import { InjectRepository } from '@mikro-orm/nestjs';
import { EntityRepository } from '@mikro-orm/core';
import { ShipmentService } from '../services/shipment.service';
import { ShipmentEventService } from '../services/shipment_event.service';
import { AddTrackingEventRequest } from '../dto/add-tracking-event-request.struct';
import { CreateShipmentRequest } from '../dto/create-shipment-request.struct';
import { FedExWebhookRequest } from '../dto/fed-ex-webhook-request.struct';
import { GetShippingRatesRequest } from '../dto/get-shipping-rates-request.struct';
import { ShipmentStatus } from '../enums/shipment-status.enum';
import { ShipmentTracking } from '../dto/shipment-tracking.struct';
import { ShippingCarrier } from '../enums/shipping-carrier.enum';
import { ShippingRateResponse } from '../dto/shipping-rate-response.struct';
import { UpdateShipmentStatusRequest } from '../dto/update-shipment-status-request.struct';
import { Shipment } from '../ecommerce_shipping_service/entities/shipping_db/shipment.entity';
import { ShipmentEvent } from '../ecommerce_shipping_service/entities/shipping_db/shipment-event.entity';
import { ShipmentItem } from '../ecommerce_shipping_service/entities/shipping_db/shipment-item.entity';
import { NotFoundException } from '@nestjs/common';
import { SqlEntityManager } from '@mikro-orm/postgresql';
import { _getRedis } from '../ecommerce_shipping_service/_cacheHelpers';
import { calculateEstimatedDelivery } from '../functions';
import { calculateRate } from '../functions';
import { generateTrackingNumber } from '../functions';
import { getEstimatedDays } from '../functions';
import { mapFedExStatus } from '../functions';
import { selectCarrier } from '../functions';
import { format } from 'date-fns';
import { producerInstance as mqProducerInstance } from '../mq/producer';
import { ApiExtraModels, ApiResponse, ApiExcludeEndpoint } from '@nestjs/swagger';

@ApiExtraModels(AddTrackingEventRequest, CreateShipmentRequest, FedExWebhookRequest, GetShippingRatesRequest, ShipmentTracking, ShippingRateResponse, UpdateShipmentStatusRequest)
@UseGuards(AuthGuard)
@Controller('api/v1/shipments')
export class ShippingAPIController {
  constructor(
    private readonly shipmentService: ShipmentService,
    private readonly shipmentEventService: ShipmentEventService,
    @InjectRepository(Shipment) private readonly shipmentRepository: EntityRepository<Shipment>,
    @InjectRepository(ShipmentEvent) private readonly shipmentEventRepository: EntityRepository<ShipmentEvent>,
    @InjectRepository(ShipmentItem) private readonly shipmentItemRepository: EntityRepository<ShipmentItem>,
  ) {}

  @Public()
  @UseGuards(InternalGuard)
  @ApiExcludeEndpoint()
  @Post('')
  @HttpCode(HttpStatus.CREATED)
  async postEndpoint(
    @Body() body: CreateShipmentRequest,
  ): Promise<Shipment> {
    let carrier: ShippingCarrier = await selectCarrier(body.destination, body.weight);
    let estimatedDelivery: Date = await calculateEstimatedDelivery(carrier, body.destination);
    const shipment = this.shipmentRepository.create({ orderId: body.orderId, trackingNumber: await generateTrackingNumber(), carrier: carrier, destination: body.destination, weight: body.weight, status: ShipmentStatus.Pending, estimatedDelivery: estimatedDelivery } as never);
    await this.shipmentRepository.getEntityManager().persistAndFlush(shipment);
    for (const item of body.items) {
      const entity = this.shipmentItemRepository.create({ shipment: shipment, productId: item.productId, quantity: item.quantity } as never);
      await this.shipmentItemRepository.getEntityManager().persistAndFlush(entity);
    }
    const entity = this.shipmentEventRepository.create({ shipment: shipment, timestamp: new Date(), status: ShipmentStatus.Pending, location: 'Warehouse', description: 'Shipment created, awaiting pickup' } as never);
    await this.shipmentEventRepository.getEntityManager().persistAndFlush(entity);
    if (mqProducerInstance !== null) {
      await mqProducerInstance.publishShipmentCreated({ shipmentId: shipment.id, orderId: body.orderId });
    }
    (await Promise.all([_getRedis().incr((String("shipments:daily:") + ':' + String(format(new Date(), 'yyyy-MM-dd')))), _getRedis().expire((String("shipments:daily:") + ':' + String(format(new Date(), 'yyyy-MM-dd'))), 86400)]))[0];
    console.info('shipment_created');
    return shipment;
  }

  @Public()
  @Post('rates')
  @HttpCode(HttpStatus.CREATED)
  @ApiResponse({ status: 201, type: [ShippingRateResponse] })
  async postRates(
    @Body() body: GetShippingRatesRequest,
  ): Promise<ShippingRateResponse[]> {
    let rates: ShippingRateResponse[] = [];
    rates.push({carrier: ShippingCarrier.FedEx, rate: await calculateRate(ShippingCarrier.FedEx, body.destination, body.weight), estimatedDays: await getEstimatedDays(ShippingCarrier.FedEx, body.destination)});
    rates.push({carrier: ShippingCarrier.Ups, rate: await calculateRate(ShippingCarrier.Ups, body.destination, body.weight), estimatedDays: await getEstimatedDays(ShippingCarrier.Ups, body.destination)});
    rates.push({carrier: ShippingCarrier.Usps, rate: await calculateRate(ShippingCarrier.Usps, body.destination, body.weight), estimatedDays: await getEstimatedDays(ShippingCarrier.Usps, body.destination)});
    return rates;
  }

  // Inbound carrier status callback. The sender is an external machine, so
  // the endpoint carries no user auth — authenticity comes from a keyed
  // hash over the raw body, verified against a logical secret handle
  // declared in config/shipping-service.dcfg before the body is trusted.
  // The carrier publishes no registry signature envelope, so the
  // sender-generic hmac scheme declares every wire detail here.
  @Public()
  @UseGuards(new WebhookVerifyGuard({"algorithm": "sha256", "encoding": "hex", "header": "X-Carrier-Signature", "mode": "hmac", "secretEnvVar": "CARRIER_WEBHOOK_SECRET"}))
  @WebhookVerify({"algorithm": "sha256", "encoding": "hex", "header": "X-Carrier-Signature", "mode": "hmac", "secretEnvVar": "CARRIER_WEBHOOK_SECRET"})
  @Post('webhook/fedex')
  @HttpCode(HttpStatus.CREATED)
  async postWebhookFedex(
    @Body() body: FedExWebhookRequest,
  ): Promise<void> {
    let trackingNumber: string = body.payload.trackingNumber;
    let eventType: string = body.payload.eventType;
    let location: string = (body.payload.location ?? 'Unknown');
    let shipment: Shipment | null = (await (this.shipmentRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Shipment, 'e_shipment').select('*').where('e_shipment.tracking_number = ?', [trackingNumber]).limit(1).getResultList())[0] ?? null;
    if ((shipment == null)) {
      console.warn('webhook_received_for_unknown_tracking_number');
      return;
    }
    let newStatus: ShipmentStatus = await mapFedExStatus(eventType);
    const entity = this.shipmentEventRepository.create({ shipment: shipment, timestamp: new Date(), status: newStatus, location: location, description: body.payload.description } as never);
    await this.shipmentEventRepository.getEntityManager().persistAndFlush(entity);
    if ((shipment.status !== newStatus)) {
      shipment.status = newStatus;
      if ((newStatus === ShipmentStatus.Delivered)) {
        shipment.actualDelivery = new Date();
      }
      await this.shipmentRepository.getEntityManager().persistAndFlush(shipment);
    }
    await _getRedis().del((String("shipment:") + ':' + String(trackingNumber)));
  }

  // Public tracking endpoint - no authentication required
  @Public()
  @Get('track/:trackingNumber')
  @ApiResponse({ status: 200, type: ShipmentTracking })
  async getTrackByTrackingNumber(
    @Param('trackingNumber') trackingNumber: string,
  ): Promise<ShipmentTracking> {
    let cached = (await (async () => {
      const _m = await _getRedis().hgetall((String("shipment:") + ':' + String(trackingNumber)));
      const out: Record<string, any> = {};
      for (const [k, v] of Object.entries(_m)) {
        out[k] = JSON.parse(String(v));
      }
      return out;
    })());
    const shipment = await (this.shipmentRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Shipment, 'e_shipment').select('*').where('e_shipment.tracking_number = ?', [trackingNumber]).getSingleResult();
    if (!shipment) {
      throw new NotFoundException("Not found");
    }
    let events: ShipmentEvent[] = await (this.shipmentEventRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(ShipmentEvent, 'e_shipment_event').select('*').where('e_shipment_event.shipment_id = ?', [shipment.id]).orderBy({ 'e_shipment_event.timestamp': 'ASC' }).getResultList();
    (await Promise.all([_getRedis().hset((String("shipment:") + ':' + String(trackingNumber)), Object.fromEntries(Object.entries({trackingNumber: trackingNumber, status: shipment.status, estimatedDelivery: shipment.estimatedDelivery}).map(([k, v]) => [String(k), JSON.stringify(v)]))), _getRedis().expire((String("shipment:") + ':' + String(trackingNumber)), 1800)]))[0];
    return Object.assign(new ShipmentTracking(), { trackingNumber: trackingNumber, status: shipment.status, carrier: shipment.carrier, destination: shipment.destination, estimatedDelivery: shipment.estimatedDelivery! ?? null, actualDelivery: shipment.actualDelivery! ?? null, events: events });
  }

  @Get('order/:orderId')
  async getOrderByOrderId(
    @Param('orderId', ParseUUIDPipe) orderId: string,
  ): Promise<Shipment> {
    const result = await (this.shipmentRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Shipment, 'e_shipment').select('*').where('e_shipment.order_id = ?', [orderId]).getSingleResult();
    if (!result) {
      throw new NotFoundException("Not found");
    }
    return result
  }

  @Get(':id/shipment_events')
  async listShipmentEvents(
    @Param('id', ParseUUIDPipe) id: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
  ): Promise<ShipmentEvent[]> {
    await this.shipmentService.findOne(id);
    return this.shipmentEventService.getByShipment(id, skip, limit);
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Post(':id/events')
  @HttpCode(HttpStatus.CREATED)
  async postByIdEvents(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: AddTrackingEventRequest,
  ): Promise<ShipmentEvent> {
    const shipment = await this.shipmentRepository.findOne({ id: id });
    if (!shipment) {
      throw new NotFoundException("Not found");
    }
    const event = this.shipmentEventRepository.create({ shipment: shipment, timestamp: new Date(), status: body.status, location: body.location, description: body.description } as never);
    await this.shipmentEventRepository.getEntityManager().persistAndFlush(event);
    if ((shipment.status !== body.status)) {
      shipment.status = body.status;
      if ((body.status === ShipmentStatus.Delivered)) {
        shipment.actualDelivery = new Date();
      }
      await this.shipmentRepository.getEntityManager().persistAndFlush(shipment);
    }
    await _getRedis().del((String("shipment:") + ':' + String(shipment.trackingNumber)));
    return event;
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Patch(':id/status')
  async putByIdStatus(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: UpdateShipmentStatusRequest,
  ): Promise<Shipment> {
    const shipment = await this.shipmentRepository.findOne({ id: id });
    if (!shipment) {
      throw new NotFoundException("Not found");
    }
    let oldStatus: ShipmentStatus = shipment.status;
    shipment.status = body.status;
    if ((body.status === ShipmentStatus.Delivered)) {
      shipment.actualDelivery = new Date();
    }
    await this.shipmentRepository.getEntityManager().persistAndFlush(shipment);
    const entity = this.shipmentEventRepository.create({ shipment: shipment, timestamp: new Date(), status: body.status, location: (body.location ?? 'Unknown'), description: (body.description ?? `Status updated to ${body.status}`) } as never);
    await this.shipmentEventRepository.getEntityManager().persistAndFlush(entity);
    // Invalidate cache on status change
    await _getRedis().del((String("shipment:") + ':' + String(shipment.trackingNumber)));
    console.info('shipment_status_updated');
    return shipment;
  }

  @Get(':id')
  async getShipment(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Shipment> {
    return this.shipmentService.findOne(id);
  }

}

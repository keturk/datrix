import { Injectable, NotFoundException, Logger, ConflictException } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { ShipmentStatus } from '../enums/shipment-status.enum'
import { ShippingCarrier } from '../enums/shipping-carrier.enum'
import { shippingDbShipmentAfterUpdate } from '../hooks/shipping-db-shipment-after-update.hook';
import { EntityManager } from '@mikro-orm/core';
import { Shipment } from '../ecommerce_shipping_service/entities/shipping_db/shipment.entity';
import { CreateShipmentDto } from '../dto/create-shipment.dto';
import { UpdateShipmentDto } from '../dto/update-shipment.dto';
import { ShipmentEvent } from '../ecommerce_shipping_service/entities/shipping_db/shipment-event.entity';

@Injectable()
export class ShipmentService {
  private readonly logger = new Logger(ShipmentService.name);

  constructor(
    private readonly em: EntityManager,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<Shipment[]> {
    this.logger.log('Finding all Shipment');
    return this.em.find(
      Shipment,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<Shipment> {
    const entity = await this.em.findOne(Shipment, { id } as never);
    if (!entity) {
      throw new NotFoundException(`Shipment with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateShipmentDto): Promise<Shipment> {
    const entity = this.em.create(Shipment, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateShipmentDto): Promise<Shipment> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
    this.em.assign(entity, dto as never);
    await this.em.flush();
    const updated = entity;
    await shippingDbShipmentAfterUpdate(updated, this.em, oldValues);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const shipmentEventCount = await this.em.count(ShipmentEvent, {
      shipment: id,
    } as never);
    if (shipmentEventCount > 0) {
      throw new ConflictException(
        `Cannot delete Shipment '${id}': ` +
        `${ shipmentEventCount } events still reference it. ` +
        `Delete or reassign ShipmentEvent records first.`,
      );
    }
    await this.em.removeAndFlush(entity);
  }

  private _fieldChanged(
    current: Shipment,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): boolean {
    if (snapshot === undefined) {
      return false;
    }
    const cur = current as unknown as Record<string, unknown>;
    return snapshot[fieldName] !== cur[fieldName];
  }

  private _fieldOldValue(
    current: Shipment,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): unknown {
    if (snapshot === undefined) {
      return undefined;
    }
    return snapshot[fieldName];
  }



  async findByOrderId(orderId: string, skip = 0, take = 100): Promise<Shipment[]> {
    return this.em.find(
      Shipment,
      { orderId } as never,
      { limit: take, offset: skip },
    );
  }
  async getByTrackingNumber(trackingNumber: string): Promise<Shipment> {
    const entity = await this.em.findOne(Shipment, {
      trackingNumber
    } as never);
    if (!entity) {
      throw new NotFoundException(`Shipment with trackingNumber ${ trackingNumber } not found`);
    }
    return entity;
  }
  async findByStatus(status: ShipmentStatus, skip = 0, take = 100): Promise<Shipment[]> {
    return this.em.find(
      Shipment,
      { status } as never,
      { limit: take, offset: skip },
    );
  }
  async findByCarrierAndStatus(carrier: ShippingCarrier, status: ShipmentStatus, skip = 0, take = 100): Promise<Shipment[]> {
    return this.em.find(
      Shipment,
      { carrier, status } as never,
      { limit: take, offset: skip },
    );
  }

}

import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { ShipmentEvent } from '../ecommerce_shipping_service/entities/shipping_db/shipment-event.entity';
import { CreateShipmentEventDto } from '../dto/create-shipment-event.dto';
import { UpdateShipmentEventDto } from '../dto/update-shipment-event.dto';

@Injectable()
export class ShipmentEventService {
  private readonly logger = new Logger(ShipmentEventService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<ShipmentEvent[]> {
    this.logger.log('Finding all ShipmentEvent');
    return this.em.find(
      ShipmentEvent,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<ShipmentEvent> {
    const entity = await this.em.findOne(ShipmentEvent, { id } as never);
    if (!entity) {
      throw new NotFoundException(`ShipmentEvent with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateShipmentEventDto): Promise<ShipmentEvent> {
    const entity = this.em.create(ShipmentEvent, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateShipmentEventDto): Promise<ShipmentEvent> {
    const entity = await this.findOne(id);
    this.em.assign(entity, dto as never);
    await this.em.flush();
    const updated = entity;
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.em.removeAndFlush(entity);
  }




  async findByShipmentId(shipmentId: string, skip = 0, take = 100): Promise<ShipmentEvent[]> {
    return this.em.find(
      ShipmentEvent,
      { shipmentId } as never,
      { limit: take, offset: skip },
    );
  }
  async findByShipmentIdAndTimestamp(shipmentId: string, timestamp: Date, skip = 0, take = 100): Promise<ShipmentEvent[]> {
    return this.em.find(
      ShipmentEvent,
      { shipmentId, timestamp } as never,
      { limit: take, offset: skip },
    );
  }

  async getByShipment(shipmentId: string, skip = 0, take = 100): Promise<ShipmentEvent[]> {
    return this.em.find(
      ShipmentEvent,
      { shipment: shipmentId } as never,
      { limit: take, offset: skip },
    );
  }
}

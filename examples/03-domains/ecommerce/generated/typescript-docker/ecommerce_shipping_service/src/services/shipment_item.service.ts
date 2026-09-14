import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { ShipmentItem } from '../ecommerce_shipping_service/entities/shipping_db/shipment-item.entity';
import { CreateShipmentItemDto } from '../dto/create-shipment-item.dto';
import { UpdateShipmentItemDto } from '../dto/update-shipment-item.dto';

@Injectable()
export class ShipmentItemService {
  private readonly logger = new Logger(ShipmentItemService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<ShipmentItem[]> {
    this.logger.log('Finding all ShipmentItem');
    return this.em.find(
      ShipmentItem,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<ShipmentItem> {
    const entity = await this.em.findOne(ShipmentItem, { id } as never);
    if (!entity) {
      throw new NotFoundException(`ShipmentItem with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateShipmentItemDto): Promise<ShipmentItem> {
    const entity = this.em.create(ShipmentItem, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateShipmentItemDto): Promise<ShipmentItem> {
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




  async findByShipmentId(shipmentId: string, skip = 0, take = 100): Promise<ShipmentItem[]> {
    return this.em.find(
      ShipmentItem,
      { shipmentId } as never,
      { limit: take, offset: skip },
    );
  }

  async getByShipment(shipmentId: string, skip = 0, take = 100): Promise<ShipmentItem[]> {
    return this.em.find(
      ShipmentItem,
      { shipment: shipmentId } as never,
      { limit: take, offset: skip },
    );
  }
}

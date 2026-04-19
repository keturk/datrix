import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { ShipmentItem } from '../entities/shipment-item.entity';
import { CreateShipmentItemDto } from '../dto/create-shipment-item.dto';
import { UpdateShipmentItemDto } from '../dto/update-shipment-item.dto';

@Injectable()
export class ShipmentItemService {
  private readonly logger = new Logger(ShipmentItemService.name);

  constructor(
    @InjectRepository(ShipmentItem)
    private readonly shipmentItemRepository: Repository<ShipmentItem>,
    private readonly dataSource: DataSource,
  ) {}

  async findAll(): Promise<ShipmentItem[]> {
    this.logger.log('Finding all ShipmentItem');
    return this.shipmentItemRepository.find();
  }

  async findOne(id: string): Promise<ShipmentItem> {
    const entity = await this.shipmentItemRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`ShipmentItem with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateShipmentItemDto): Promise<ShipmentItem> {
    const entity = this.shipmentItemRepository.create(dto);
    const saved = await this.shipmentItemRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateShipmentItemDto): Promise<ShipmentItem> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    const updated = await this.shipmentItemRepository.save(entity);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.shipmentItemRepository.remove(entity);
  }





  async getByShipment(shipmentId: string, skip = 0, take = 100): Promise<ShipmentItem[]> {
    return this.shipmentItemRepository.find({ where: { shipmentId } as any, skip, take });
  }
}

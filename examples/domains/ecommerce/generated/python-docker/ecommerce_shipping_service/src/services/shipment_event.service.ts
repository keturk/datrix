import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { ShipmentEvent } from '../entities/shipment-event.entity';
import { CreateShipmentEventDto } from '../dto/create-shipment-event.dto';
import { UpdateShipmentEventDto } from '../dto/update-shipment-event.dto';

@Injectable()
export class ShipmentEventService {
  private readonly logger = new Logger(ShipmentEventService.name);

  constructor(
    @InjectRepository(ShipmentEvent)
    private readonly shipmentEventRepository: Repository<ShipmentEvent>,
    private readonly dataSource: DataSource,
  ) {}

  async findAll(): Promise<ShipmentEvent[]> {
    this.logger.log('Finding all ShipmentEvent');
    return this.shipmentEventRepository.find();
  }

  async findOne(id: string): Promise<ShipmentEvent> {
    const entity = await this.shipmentEventRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`ShipmentEvent with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateShipmentEventDto): Promise<ShipmentEvent> {
    const entity = this.shipmentEventRepository.create(dto);
    const saved = await this.shipmentEventRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateShipmentEventDto): Promise<ShipmentEvent> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    const updated = await this.shipmentEventRepository.save(entity);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.shipmentEventRepository.remove(entity);
  }




  async findByShipmentIdAndTimestamp(shipmentId: string, timestamp: Date, skip = 0, take = 100): Promise<ShipmentEvent[]> {
    return this.shipmentEventRepository.find({
      where: { shipmentId, timestamp } as any,
      skip,
      take,
    });
  }

  async getByShipment(shipmentId: string, skip = 0, take = 100): Promise<ShipmentEvent[]> {
    return this.shipmentEventRepository.find({ where: { shipmentId } as any, skip, take });
  }
}

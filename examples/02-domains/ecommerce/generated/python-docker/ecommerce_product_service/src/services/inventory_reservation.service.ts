import { Injectable, NotFoundException, Logger, BadRequestException } from '@nestjs/common';
import { ReservationStatus } from '../enums/reservation-status.enum'
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { InventoryReservation } from '../entities/inventory-reservation.entity';
import { CreateInventoryReservationDto } from '../dto/create-inventory-reservation.dto';
import { UpdateInventoryReservationDto } from '../dto/update-inventory-reservation.dto';

@Injectable()
export class InventoryReservationService {
  private readonly logger = new Logger(InventoryReservationService.name);

  constructor(
    @InjectRepository(InventoryReservation)
    private readonly inventoryReservationRepository: Repository<InventoryReservation>,
    private readonly dataSource: DataSource,
  ) {}

  async findAll(): Promise<InventoryReservation[]> {
    this.logger.log('Finding all InventoryReservation');
    return this.inventoryReservationRepository.find();
  }

  async findOne(id: string): Promise<InventoryReservation> {
    const entity = await this.inventoryReservationRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`InventoryReservation with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateInventoryReservationDto): Promise<InventoryReservation> {
    const entity = this.inventoryReservationRepository.create(dto);
    this._validate(entity);
    const saved = await this.inventoryReservationRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateInventoryReservationDto): Promise<InventoryReservation> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    this._validate(entity);
    const updated = await this.inventoryReservationRepository.save(entity);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.inventoryReservationRepository.remove(entity);
  }



  private _validate(entity: InventoryReservation): void {
    const errors: string[] = [];
    if (((entity.quantity <= 0))) {
      errors.push('Reservation quantity must be positive');
    }
    if (errors.length > 0) {
      throw new BadRequestException(errors.join('; '));
    }
  }

  async findByReservationId(reservationId: string, skip = 0, take = 100): Promise<InventoryReservation[]> {
    return this.inventoryReservationRepository.find({ where: { reservationId } as any, skip, take });
  }
  async findByExpiresAt(expiresAt: Date, skip = 0, take = 100): Promise<InventoryReservation[]> {
    return this.inventoryReservationRepository.find({ where: { expiresAt } as any, skip, take });
  }
  async findByReservationIdAndStatus(reservationId: string, status: ReservationStatus, skip = 0, take = 100): Promise<InventoryReservation[]> {
    return this.inventoryReservationRepository.find({
      where: { reservationId, status } as any,
      skip,
      take,
    });
  }

  async getByProduct(productId: string, skip = 0, take = 100): Promise<InventoryReservation[]> {
    return this.inventoryReservationRepository.find({ where: { productId } as any, skip, take });
  }
}

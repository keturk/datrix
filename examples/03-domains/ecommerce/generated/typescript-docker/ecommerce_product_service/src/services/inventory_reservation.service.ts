import { Injectable, NotFoundException, Logger, BadRequestException } from '@nestjs/common';
import { ReservationStatus } from '../enums/reservation-status.enum'
import { EntityManager } from '@mikro-orm/core';
import { InventoryReservation } from '../ecommerce_product_service/entities/product_db/inventory-reservation.entity';
import { CreateInventoryReservationDto } from '../dto/create-inventory-reservation.dto';
import { UpdateInventoryReservationDto } from '../dto/update-inventory-reservation.dto';

@Injectable()
export class InventoryReservationService {
  private readonly logger = new Logger(InventoryReservationService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<InventoryReservation[]> {
    this.logger.log('Finding all InventoryReservation');
    return this.em.find(
      InventoryReservation,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<InventoryReservation> {
    const entity = await this.em.findOne(InventoryReservation, { id } as never);
    if (!entity) {
      throw new NotFoundException(`InventoryReservation with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateInventoryReservationDto): Promise<InventoryReservation> {
    const entity = this.em.create(InventoryReservation, dto as never);
    this._validate(entity);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateInventoryReservationDto): Promise<InventoryReservation> {
    const entity = await this.findOne(id);
    this.em.assign(entity, dto as never);
    this._validate(entity);
    await this.em.flush();
    const updated = entity;
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.em.removeAndFlush(entity);
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
    return this.em.find(
      InventoryReservation,
      { reservationId } as never,
      { limit: take, offset: skip },
    );
  }
  async findByExpiresAt(expiresAt: Date, skip = 0, take = 100): Promise<InventoryReservation[]> {
    return this.em.find(
      InventoryReservation,
      { expiresAt } as never,
      { limit: take, offset: skip },
    );
  }
  async findByProductId(productId: string, skip = 0, take = 100): Promise<InventoryReservation[]> {
    return this.em.find(
      InventoryReservation,
      { productId } as never,
      { limit: take, offset: skip },
    );
  }
  async findByReservationIdAndStatus(reservationId: string, status: ReservationStatus, skip = 0, take = 100): Promise<InventoryReservation[]> {
    return this.em.find(
      InventoryReservation,
      { reservationId, status } as never,
      { limit: take, offset: skip },
    );
  }

  async getByProduct(productId: string, skip = 0, take = 100): Promise<InventoryReservation[]> {
    return this.em.find(
      InventoryReservation,
      { product: productId } as never,
      { limit: take, offset: skip },
    );
  }
}

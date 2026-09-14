import { Injectable, NotFoundException, Logger, BadRequestException } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { IdempotencyKey } from '../ecommerce_order_service/entities/order_db/idempotency-key.entity';
import { CreateIdempotencyKeyDto } from '../dto/create-idempotency-key.dto';
import { UpdateIdempotencyKeyDto } from '../dto/update-idempotency-key.dto';

@Injectable()
export class IdempotencyKeyService {
  private readonly logger = new Logger(IdempotencyKeyService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<IdempotencyKey[]> {
    this.logger.log('Finding all IdempotencyKey');
    return this.em.find(
      IdempotencyKey,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<IdempotencyKey> {
    const entity = await this.em.findOne(IdempotencyKey, { id } as never);
    if (!entity) {
      throw new NotFoundException(`IdempotencyKey with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateIdempotencyKeyDto): Promise<IdempotencyKey> {
    const entity = this.em.create(IdempotencyKey, dto as never);
    this._validate(entity);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateIdempotencyKeyDto): Promise<IdempotencyKey> {
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



  private _validate(entity: IdempotencyKey): void {
    const errors: string[] = [];
    if (((entity.key.trim().length === 0))) {
      errors.push('Idempotency key cannot be empty');
    }
    if (errors.length > 0) {
      throw new BadRequestException(errors.join('; '));
    }
  }

  async getByKey(key: string): Promise<IdempotencyKey> {
    const entity = await this.em.findOne(IdempotencyKey, {
      key
    } as never);
    if (!entity) {
      throw new NotFoundException(`IdempotencyKey with key ${ key } not found`);
    }
    return entity;
  }
  async findByOperation(operation: string, skip = 0, take = 100): Promise<IdempotencyKey[]> {
    return this.em.find(
      IdempotencyKey,
      { operation } as never,
      { limit: take, offset: skip },
    );
  }
  async findByExpiresAt(expiresAt: Date, skip = 0, take = 100): Promise<IdempotencyKey[]> {
    return this.em.find(
      IdempotencyKey,
      { expiresAt } as never,
      { limit: take, offset: skip },
    );
  }

}

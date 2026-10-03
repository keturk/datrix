import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { ApiKey } from '../ecommerce_user_service/entities/user_db/api-key.entity';
import { CreateApiKeyDto } from '../dto/create-api-key.dto';
import { UpdateApiKeyDto } from '../dto/update-api-key.dto';

@Injectable()
export class ApiKeyService {
  private readonly logger = new Logger(ApiKeyService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<ApiKey[]> {
    this.logger.log('Finding all ApiKey');
    return this.em.find(
      ApiKey,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<ApiKey> {
    const entity = await this.em.findOne(ApiKey, { id } as never);
    if (!entity) {
      throw new NotFoundException(`ApiKey with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateApiKeyDto): Promise<ApiKey> {
    const entity = this.em.create(ApiKey, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateApiKeyDto): Promise<ApiKey> {
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



  async getByKeyHash(keyHash: string): Promise<ApiKey> {
    const entity = await this.em.findOne(ApiKey, {
      keyHash    } as never);
    if (!entity) {
      throw new NotFoundException(`ApiKey with keyHash ${ keyHash } not found`);
    }
    return entity;
  }
  async findByOwnerId(ownerId: string, skip = 0, take = 100): Promise<ApiKey[]> {
    return this.em.find(
      ApiKey,
      { ownerId } as never,
      { limit: take, offset: skip },
    );
  }

}

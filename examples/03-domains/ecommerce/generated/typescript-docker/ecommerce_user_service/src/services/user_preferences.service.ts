import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { UserPreferences } from '../ecommerce_user_service/entities/user_db/user-preferences.entity';
import { CreateUserPreferencesDto } from '../dto/create-user-preferences.dto';
import { UpdateUserPreferencesDto } from '../dto/update-user-preferences.dto';

@Injectable()
export class UserPreferencesService {
  private readonly logger = new Logger(UserPreferencesService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<UserPreferences[]> {
    this.logger.log('Finding all UserPreferences');
    return this.em.find(
      UserPreferences,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<UserPreferences> {
    const entity = await this.em.findOne(UserPreferences, { id } as never);
    if (!entity) {
      throw new NotFoundException(`UserPreferences with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateUserPreferencesDto): Promise<UserPreferences> {
    const entity = this.em.create(UserPreferences, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateUserPreferencesDto): Promise<UserPreferences> {
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





  async getByUser(userId: string, skip = 0, take = 100): Promise<UserPreferences[]> {
    return this.em.find(
      UserPreferences,
      { user: userId } as never,
      { limit: take, offset: skip },
    );
  }
}

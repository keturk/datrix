import { Injectable, NotFoundException, Logger, BadRequestException } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { UserSession } from '../ecommerce_user_service/entities/user_db/user-session.entity';
import { CreateUserSessionDto } from '../dto/create-user-session.dto';
import { UpdateUserSessionDto } from '../dto/update-user-session.dto';

@Injectable()
export class UserSessionService {
  private readonly logger = new Logger(UserSessionService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<UserSession[]> {
    this.logger.log('Finding all UserSession');
    return this.em.find(
      UserSession,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<UserSession> {
    const entity = await this.em.findOne(UserSession, { id } as never);
    if (!entity) {
      throw new NotFoundException(`UserSession with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateUserSessionDto): Promise<UserSession> {
    const entity = this.em.create(UserSession, dto as never);
    if (entity.createdAt === undefined || entity.createdAt === null) {
      entity.createdAt = new Date();
    }
    this._validate(entity);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateUserSessionDto): Promise<UserSession> {
    const entity = await this.findOne(id);
    this.em.assign(entity, dto as never);
    if (entity.createdAt === undefined || entity.createdAt === null) {
      entity.createdAt = new Date();
    }
    this._validate(entity);
    await this.em.flush();
    const updated = entity;
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.em.removeAndFlush(entity);
  }



  private _validate(entity: UserSession): void {
    const errors: string[] = [];
    if ((entity.createdAt !== undefined && entity.createdAt !== null) && ((entity.expiresAt <= entity.createdAt))) {
      errors.push('Expiry must be after creation');
    }
    if (errors.length > 0) {
      throw new BadRequestException(errors.join('; '));
    }
  }

  async getByToken(token: string): Promise<UserSession> {
    const entity = await this.em.findOne(UserSession, {
      token
    } as never);
    if (!entity) {
      throw new NotFoundException(`UserSession with token ${ token } not found`);
    }
    return entity;
  }
  async findByUserId(userId: string, skip = 0, take = 100): Promise<UserSession[]> {
    return this.em.find(
      UserSession,
      { userId } as never,
      { limit: take, offset: skip },
    );
  }
  async findByUserIdAndExpiresAt(userId: string, expiresAt: Date, skip = 0, take = 100): Promise<UserSession[]> {
    return this.em.find(
      UserSession,
      { userId, expiresAt } as never,
      { limit: take, offset: skip },
    );
  }

  async getByUser(userId: string, skip = 0, take = 100): Promise<UserSession[]> {
    return this.em.find(
      UserSession,
      { user: userId } as never,
      { limit: take, offset: skip },
    );
  }
}

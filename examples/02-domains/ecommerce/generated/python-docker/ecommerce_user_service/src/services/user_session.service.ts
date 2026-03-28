import { Injectable, NotFoundException, Logger, BadRequestException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { UserSession } from '../entities/user-session.entity';
import { CreateUserSessionDto } from '../dto/create-user-session.dto';
import { UpdateUserSessionDto } from '../dto/update-user-session.dto';

@Injectable()
export class UserSessionService {
  private readonly logger = new Logger(UserSessionService.name);

  constructor(
    @InjectRepository(UserSession)
    private readonly userSessionRepository: Repository<UserSession>,
    private readonly dataSource: DataSource,
  ) {}

  async findAll(): Promise<UserSession[]> {
    this.logger.log('Finding all UserSession');
    return this.userSessionRepository.find();
  }

  async findOne(id: string): Promise<UserSession> {
    const entity = await this.userSessionRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`UserSession with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateUserSessionDto): Promise<UserSession> {
    const entity = this.userSessionRepository.create(dto);
    if (entity.createdAt === undefined || entity.createdAt === null) {
      entity.createdAt = new Date();
    }
    this._validate(entity);
    const saved = await this.userSessionRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateUserSessionDto): Promise<UserSession> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    if (entity.createdAt === undefined || entity.createdAt === null) {
      entity.createdAt = new Date();
    }
    this._validate(entity);
    const updated = await this.userSessionRepository.save(entity);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.userSessionRepository.remove(entity);
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
    const entity = await this.userSessionRepository.findOne({ where: { token } as any });
    if (!entity) {
      throw new NotFoundException(`UserSession with token ${ token } not found`);
    }
    return entity;
  }
  async findByUserIdAndExpiresAt(userId: string, expiresAt: Date, skip = 0, take = 100): Promise<UserSession[]> {
    return this.userSessionRepository.find({
      where: { userId, expiresAt } as any,
      skip,
      take,
    });
  }

  async getByUser(userId: string, skip = 0, take = 100): Promise<UserSession[]> {
    return this.userSessionRepository.find({ where: { userId } as any, skip, take });
  }
}

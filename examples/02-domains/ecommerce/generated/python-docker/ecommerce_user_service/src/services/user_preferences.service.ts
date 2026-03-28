import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { UserPreferences } from '../entities/user-preferences.entity';
import { CreateUserPreferencesDto } from '../dto/create-user-preferences.dto';
import { UpdateUserPreferencesDto } from '../dto/update-user-preferences.dto';

@Injectable()
export class UserPreferencesService {
  private readonly logger = new Logger(UserPreferencesService.name);

  constructor(
    @InjectRepository(UserPreferences)
    private readonly userPreferencesRepository: Repository<UserPreferences>,
    private readonly dataSource: DataSource,
  ) {}

  async findAll(): Promise<UserPreferences[]> {
    this.logger.log('Finding all UserPreferences');
    return this.userPreferencesRepository.find();
  }

  async findOne(id: string): Promise<UserPreferences> {
    const entity = await this.userPreferencesRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`UserPreferences with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateUserPreferencesDto): Promise<UserPreferences> {
    const entity = this.userPreferencesRepository.create(dto);
    const saved = await this.userPreferencesRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateUserPreferencesDto): Promise<UserPreferences> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    const updated = await this.userPreferencesRepository.save(entity);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.userPreferencesRepository.remove(entity);
  }





  async getByUser(userId: string, skip = 0, take = 100): Promise<UserPreferences[]> {
    return this.userPreferencesRepository.find({ where: { userId } as any, skip, take });
  }
}

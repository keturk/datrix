import { Injectable, NotFoundException, Logger, BadRequestException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { IdempotencyKey } from '../entities/idempotency-key.entity';
import { CreateIdempotencyKeyDto } from '../dto/create-idempotency-key.dto';
import { UpdateIdempotencyKeyDto } from '../dto/update-idempotency-key.dto';

@Injectable()
export class IdempotencyKeyService {
  private readonly logger = new Logger(IdempotencyKeyService.name);

  constructor(
    @InjectRepository(IdempotencyKey)
    private readonly idempotencyKeyRepository: Repository<IdempotencyKey>,
    private readonly dataSource: DataSource,
  ) {}

  async findAll(): Promise<IdempotencyKey[]> {
    this.logger.log('Finding all IdempotencyKey');
    return this.idempotencyKeyRepository.find();
  }

  async findOne(id: string): Promise<IdempotencyKey> {
    const entity = await this.idempotencyKeyRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`IdempotencyKey with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateIdempotencyKeyDto): Promise<IdempotencyKey> {
    const entity = this.idempotencyKeyRepository.create(dto);
    this._validate(entity);
    const saved = await this.idempotencyKeyRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateIdempotencyKeyDto): Promise<IdempotencyKey> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    this._validate(entity);
    const updated = await this.idempotencyKeyRepository.save(entity);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.idempotencyKeyRepository.remove(entity);
  }



  private _validate(entity: IdempotencyKey): void {
    const errors: string[] = [];
    if ((entity.key.trim().length === 0)) {
      errors.push('Idempotency key cannot be empty');
    }
    if (errors.length > 0) {
      throw new BadRequestException(errors.join('; '));
    }
  }

  async getByKey(key: string): Promise<IdempotencyKey> {
    const entity = await this.idempotencyKeyRepository.findOne({ where: { key } as any });
    if (!entity) {
      throw new NotFoundException(`IdempotencyKey with key ${ key } not found`);
    }
    return entity;
  }
  async findByOperation(operation: string, skip = 0, take = 100): Promise<IdempotencyKey[]> {
    return this.idempotencyKeyRepository.find({ where: { operation } as any, skip, take });
  }
  async findByExpiresAt(expiresAt: Date, skip = 0, take = 100): Promise<IdempotencyKey[]> {
    return this.idempotencyKeyRepository.find({ where: { expiresAt } as any, skip, take });
  }

}

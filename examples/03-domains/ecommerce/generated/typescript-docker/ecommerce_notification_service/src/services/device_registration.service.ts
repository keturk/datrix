import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { DeviceRegistration } from '../ecommerce_notification_service/entities/notification_db/device-registration.entity';
import { CreateDeviceRegistrationDto } from '../dto/create-device-registration.dto';
import { UpdateDeviceRegistrationDto } from '../dto/update-device-registration.dto';

@Injectable()
export class DeviceRegistrationService {
  private readonly logger = new Logger(DeviceRegistrationService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<DeviceRegistration[]> {
    this.logger.log('Finding all DeviceRegistration');
    return this.em.find(
      DeviceRegistration,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<DeviceRegistration> {
    const entity = await this.em.findOne(DeviceRegistration, { id } as never);
    if (!entity) {
      throw new NotFoundException(`DeviceRegistration with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateDeviceRegistrationDto): Promise<DeviceRegistration> {
    const entity = this.em.create(DeviceRegistration, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateDeviceRegistrationDto): Promise<DeviceRegistration> {
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



  async findBySubject(subject: string, skip = 0, take = 100): Promise<DeviceRegistration[]> {
    return this.em.find(
      DeviceRegistration,
      { subject } as never,
      { limit: take, offset: skip },
    );
  }

}

import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { NotificationAudit } from '../ecommerce_notification_service/entities/notification_db/notification-audit.entity';
import { CreateNotificationAuditDto } from '../dto/create-notification-audit.dto';
import { UpdateNotificationAuditDto } from '../dto/update-notification-audit.dto';

@Injectable()
export class NotificationAuditService {
  private readonly logger = new Logger(NotificationAuditService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<NotificationAudit[]> {
    this.logger.log('Finding all NotificationAudit');
    return this.em.find(
      NotificationAudit,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<NotificationAudit> {
    const entity = await this.em.findOne(NotificationAudit, { id } as never);
    if (!entity) {
      throw new NotFoundException(`NotificationAudit with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateNotificationAuditDto): Promise<NotificationAudit> {
    const entity = this.em.create(NotificationAudit, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateNotificationAuditDto): Promise<NotificationAudit> {
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




  async findByOrderId(orderId: string, skip = 0, take = 100): Promise<NotificationAudit[]> {
    return this.em.find(
      NotificationAudit,
      { orderId } as never,
      { limit: take, offset: skip },
    );
  }

}

import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { Refund } from '../ecommerce_payment_service/entities/payment_db/refund.entity';
import { CreateRefundDto } from '../dto/create-refund.dto';
import { UpdateRefundDto } from '../dto/update-refund.dto';

@Injectable()
export class RefundService {
  private readonly logger = new Logger(RefundService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<Refund[]> {
    this.logger.log('Finding all Refund');
    return this.em.find(
      Refund,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<Refund> {
    const entity = await this.em.findOne(Refund, { id } as never);
    if (!entity) {
      throw new NotFoundException(`Refund with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateRefundDto): Promise<Refund> {
    const entity = this.em.create(Refund, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateRefundDto): Promise<Refund> {
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




  async findByPaymentId(paymentId: string, skip = 0, take = 100): Promise<Refund[]> {
    return this.em.find(
      Refund,
      { paymentId } as never,
      { limit: take, offset: skip },
    );
  }

  async getByPayment(paymentId: string, skip = 0, take = 100): Promise<Refund[]> {
    return this.em.find(
      Refund,
      { payment: paymentId } as never,
      { limit: take, offset: skip },
    );
  }
}

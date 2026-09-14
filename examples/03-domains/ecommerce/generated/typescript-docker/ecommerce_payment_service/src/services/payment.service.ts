import { Injectable, NotFoundException, Logger, ConflictException } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { PaymentStatus } from '../enums/payment-status.enum'
import { paymentDbPaymentAfterUpdate } from '../hooks/payment-db-payment-after-update.hook';
import { EntityManager } from '@mikro-orm/core';
import { Payment } from '../ecommerce_payment_service/entities/payment_db/payment.entity';
import { CreatePaymentDto } from '../dto/create-payment.dto';
import { UpdatePaymentDto } from '../dto/update-payment.dto';
import { Refund } from '../ecommerce_payment_service/entities/payment_db/refund.entity';

@Injectable()
export class PaymentService {
  private readonly logger = new Logger(PaymentService.name);

  constructor(
    private readonly em: EntityManager,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<Payment[]> {
    this.logger.log('Finding all Payment');
    return this.em.find(
      Payment,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<Payment> {
    const entity = await this.em.findOne(Payment, { id } as never);
    if (!entity) {
      throw new NotFoundException(`Payment with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreatePaymentDto): Promise<Payment> {
    const entity = this.em.create(Payment, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdatePaymentDto): Promise<Payment> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
    this.em.assign(entity, dto as never);
    await this.em.flush();
    const updated = entity;
    await paymentDbPaymentAfterUpdate(updated, this.em, oldValues);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const refundCount = await this.em.count(Refund, {
      payment: id,
    } as never);
    if (refundCount > 0) {
      throw new ConflictException(
        `Cannot delete Payment '${id}': ` +
        `${ refundCount } refunds still reference it. ` +
        `Delete or reassign Refund records first.`,
      );
    }
    await this.em.removeAndFlush(entity);
  }

  private _fieldChanged(
    current: Payment,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): boolean {
    if (snapshot === undefined) {
      return false;
    }
    const cur = current as unknown as Record<string, unknown>;
    return snapshot[fieldName] !== cur[fieldName];
  }

  private _fieldOldValue(
    current: Payment,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): unknown {
    if (snapshot === undefined) {
      return undefined;
    }
    return snapshot[fieldName];
  }



  async findByOrderId(orderId: string, skip = 0, take = 100): Promise<Payment[]> {
    return this.em.find(
      Payment,
      { orderId } as never,
      { limit: take, offset: skip },
    );
  }
  async findByCustomerId(customerId: string, skip = 0, take = 100): Promise<Payment[]> {
    return this.em.find(
      Payment,
      { customerId } as never,
      { limit: take, offset: skip },
    );
  }
  async getByTransactionId(transactionId: string): Promise<Payment> {
    const entity = await this.em.findOne(Payment, {
      transactionId
    } as never);
    if (!entity) {
      throw new NotFoundException(`Payment with transactionId ${ transactionId } not found`);
    }
    return entity;
  }
  async findByCustomerIdAndStatus(customerId: string, status: PaymentStatus, skip = 0, take = 100): Promise<Payment[]> {
    return this.em.find(
      Payment,
      { customerId, status } as never,
      { limit: take, offset: skip },
    );
  }

}

import { Injectable, NotFoundException, Logger, ConflictException } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { PaymentFailedEvent } from '../events/payment-failed.event';
import { PaymentProcessedEvent } from '../events/payment-processed.event';
import { PaymentRefundedEvent } from '../events/payment-refunded.event';
import { PaymentStatus } from '../enums/payment-status.enum'
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { Payment } from '../entities/payment.entity';
import { CreatePaymentDto } from '../dto/create-payment.dto';
import { UpdatePaymentDto } from '../dto/update-payment.dto';
import { Refund } from '../entities/refund.entity';

@Injectable()
export class PaymentService {
  private readonly logger = new Logger(PaymentService.name);

  constructor(
    @InjectRepository(Payment)
    private readonly paymentRepository: Repository<Payment>,
    private readonly dataSource: DataSource,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(): Promise<Payment[]> {
    this.logger.log('Finding all Payment');
    return this.paymentRepository.find();
  }

  async findOne(id: string): Promise<Payment> {
    const entity = await this.paymentRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`Payment with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreatePaymentDto): Promise<Payment> {
    const entity = this.paymentRepository.create(dto);
    const saved = await this.paymentRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdatePaymentDto): Promise<Payment> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
    Object.assign(entity, dto);
    const updated = await this.paymentRepository.save(entity);
if (this._fieldChanged(updated, "status", oldValues)) {
  if ((updated.status === PaymentStatus.Completed)) {
    this.eventEmitter.emit('PaymentProcessed', new PaymentProcessedEvent({ paymentId: updated.id, orderId: updated.orderId, amount: updated.amount }));
  } else if ((updated.status === PaymentStatus.Failed)) {
    this.eventEmitter.emit('PaymentFailed', new PaymentFailedEvent({ paymentId: updated.id, orderId: updated.orderId, reason: (updated.errorMessage ?? 'Payment failed') }));
  } else if ((updated.status === PaymentStatus.Refunded)) {
    this.eventEmitter.emit('PaymentRefunded', new PaymentRefundedEvent({ paymentId: updated.id, orderId: updated.orderId, amount: updated.amount }));
  }
}
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const refundCount = await this.dataSource
      .getRepository(Refund)
      .count({ where: { paymentId: id } as any });
    if (refundCount > 0) {
      throw new ConflictException(
        `Cannot delete Payment '${id}': ` +
        `${ refundCount } refunds still reference it. ` +
        `Delete or reassign Refund records first.`,
      );
    }
    await this.paymentRepository.remove(entity);
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
    return this.paymentRepository.find({ where: { orderId } as any, skip, take });
  }
  async findByCustomerId(customerId: string, skip = 0, take = 100): Promise<Payment[]> {
    return this.paymentRepository.find({ where: { customerId } as any, skip, take });
  }
  async getByTransactionId(transactionId: string): Promise<Payment> {
    const entity = await this.paymentRepository.findOne({ where: { transactionId } as any });
    if (!entity) {
      throw new NotFoundException(`Payment with transactionId ${ transactionId } not found`);
    }
    return entity;
  }
  async findByCustomerIdAndStatus(customerId: string, status: PaymentStatus, skip = 0, take = 100): Promise<Payment[]> {
    return this.paymentRepository.find({
      where: { customerId, status } as any,
      skip,
      take,
    });
  }

}

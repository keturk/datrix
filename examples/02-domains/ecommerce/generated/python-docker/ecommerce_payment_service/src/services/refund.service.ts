import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { Refund } from '../entities/refund.entity';
import { CreateRefundDto } from '../dto/create-refund.dto';
import { UpdateRefundDto } from '../dto/update-refund.dto';

@Injectable()
export class RefundService {
  private readonly logger = new Logger(RefundService.name);

  constructor(
    @InjectRepository(Refund)
    private readonly refundRepository: Repository<Refund>,
    private readonly dataSource: DataSource,
  ) {}

  async findAll(): Promise<Refund[]> {
    this.logger.log('Finding all Refund');
    return this.refundRepository.find();
  }

  async findOne(id: string): Promise<Refund> {
    const entity = await this.refundRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`Refund with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateRefundDto): Promise<Refund> {
    const entity = this.refundRepository.create(dto);
    const saved = await this.refundRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateRefundDto): Promise<Refund> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    const updated = await this.refundRepository.save(entity);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.refundRepository.remove(entity);
  }





  async getByPayment(paymentId: string, skip = 0, take = 100): Promise<Refund[]> {
    return this.refundRepository.find({ where: { paymentId } as any, skip, take });
  }
}

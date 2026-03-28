import { Injectable, NotFoundException, Logger, BadRequestException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { OrderItem } from '../entities/order-item.entity';
import { CreateOrderItemDto } from '../dto/create-order-item.dto';
import { UpdateOrderItemDto } from '../dto/update-order-item.dto';

@Injectable()
export class OrderItemService {
  private readonly logger = new Logger(OrderItemService.name);

  constructor(
    @InjectRepository(OrderItem)
    private readonly orderItemRepository: Repository<OrderItem>,
    private readonly dataSource: DataSource,
  ) {}

  async findAll(): Promise<OrderItem[]> {
    this.logger.log('Finding all OrderItem');
    return this.orderItemRepository.find();
  }

  async findOne(id: string): Promise<OrderItem> {
    const entity = await this.orderItemRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`OrderItem with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateOrderItemDto): Promise<OrderItem> {
    const entity = this.orderItemRepository.create(dto);
    this._validate(entity);
    const saved = await this.orderItemRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateOrderItemDto): Promise<OrderItem> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    this._validate(entity);
    const updated = await this.orderItemRepository.save(entity);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.orderItemRepository.remove(entity);
  }



  private _validate(entity: OrderItem): void {
    const errors: string[] = [];
    if (((entity.quantity <= 0))) {
      errors.push('Quantity must be greater than 0');
    }
    if (((entity.quantity > 100))) {
      errors.push('Quantity cannot exceed 100 per item');
    }
    if (((entity.unitPrice.amount < 0))) {
      errors.push('Unit price cannot be negative');
    }
    if (errors.length > 0) {
      throw new BadRequestException(errors.join('; '));
    }
  }

  async findByProductId(productId: string, skip = 0, take = 100): Promise<OrderItem[]> {
    return this.orderItemRepository.find({ where: { productId } as any, skip, take });
  }

  async getByOrder(orderId: string, skip = 0, take = 100): Promise<OrderItem[]> {
    return this.orderItemRepository.find({ where: { orderId } as any, skip, take });
  }
}

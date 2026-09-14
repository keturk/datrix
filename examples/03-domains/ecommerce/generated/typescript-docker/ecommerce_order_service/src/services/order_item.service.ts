import { Injectable, NotFoundException, Logger, BadRequestException } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { OrderItem } from '../ecommerce_order_service/entities/order_db/order-item.entity';
import { CreateOrderItemDto } from '../dto/create-order-item.dto';
import { UpdateOrderItemDto } from '../dto/update-order-item.dto';

@Injectable()
export class OrderItemService {
  private readonly logger = new Logger(OrderItemService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<OrderItem[]> {
    this.logger.log('Finding all OrderItem');
    return this.em.find(
      OrderItem,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<OrderItem> {
    const entity = await this.em.findOne(OrderItem, { id } as never);
    if (!entity) {
      throw new NotFoundException(`OrderItem with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateOrderItemDto): Promise<OrderItem> {
    const entity = this.em.create(OrderItem, dto as never);
    this._validate(entity);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateOrderItemDto): Promise<OrderItem> {
    const entity = await this.findOne(id);
    this.em.assign(entity, dto as never);
    this._validate(entity);
    await this.em.flush();
    const updated = entity;
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.em.removeAndFlush(entity);
  }



  private _validate(entity: OrderItem): void {
    const errors: string[] = [];
    if (((entity.quantity <= 0))) {
      errors.push('Quantity must be greater than 0');
    }
    if (((entity.quantity > 100))) {
      errors.push('Quantity cannot exceed 100 per item');
    }
    if (((entity.unitPrice < 0))) {
      errors.push('Unit price cannot be negative');
    }
    if (errors.length > 0) {
      throw new BadRequestException(errors.join('; '));
    }
  }

  async findByProductId(productId: string, skip = 0, take = 100): Promise<OrderItem[]> {
    return this.em.find(
      OrderItem,
      { productId } as never,
      { limit: take, offset: skip },
    );
  }
  async findByOrderId(orderId: string, skip = 0, take = 100): Promise<OrderItem[]> {
    return this.em.find(
      OrderItem,
      { orderId } as never,
      { limit: take, offset: skip },
    );
  }

  async getByOrder(orderId: string, skip = 0, take = 100): Promise<OrderItem[]> {
    return this.em.find(
      OrderItem,
      { order: orderId } as never,
      { limit: take, offset: skip },
    );
  }
}

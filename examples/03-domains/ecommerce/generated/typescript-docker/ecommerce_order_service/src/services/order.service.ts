import { Injectable, NotFoundException, Logger, ConflictException, BadRequestException } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { OrderStatus } from '../enums/order-status.enum'
import { orderDbOrderAfterCreate } from '../hooks/order-db-order-after-create.hook';
import { orderDbOrderAfterUpdate } from '../hooks/order-db-order-after-update.hook';
import { EntityManager } from '@mikro-orm/core';
import { Order } from '../ecommerce_order_service/entities/order_db/order.entity';
import { CreateOrderDto } from '../dto/create-order.dto';
import { UpdateOrderDto } from '../dto/update-order.dto';
import { OrderItem } from '../ecommerce_order_service/entities/order_db/order-item.entity';

@Injectable()
export class OrderService {
  private readonly logger = new Logger(OrderService.name);

  constructor(
    private readonly em: EntityManager,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<Order[]> {
    this.logger.log('Finding all Order');
    return this.em.find(
      Order,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<Order> {
    const entity = await this.em.findOne(Order, { id } as never);
    if (!entity) {
      throw new NotFoundException(`Order with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateOrderDto): Promise<Order> {
    const entity = this.em.create(Order, dto as never);
    this._validate(entity);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    await orderDbOrderAfterCreate(saved, this.em!);
    return saved;
  }

  async update(id: string, dto: UpdateOrderDto): Promise<Order> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
    this.em.assign(entity, dto as never);
    this._validate(entity);
    await this.em.flush();
    const updated = entity;
    await orderDbOrderAfterUpdate(updated, this.em, oldValues);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const orderItemCount = await this.em.count(OrderItem, {
      order: id,
    } as never);
    if (orderItemCount > 0) {
      throw new ConflictException(
        `Cannot delete Order '${id}': ` +
        `${ orderItemCount } items still reference it. ` +
        `Delete or reassign OrderItem records first.`,
      );
    }
    await this.em.removeAndFlush(entity);
  }

  private _fieldChanged(
    current: Order,
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
    current: Order,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): unknown {
    if (snapshot === undefined) {
      return undefined;
    }
    return snapshot[fieldName];
  }


  private _validate(entity: Order): void {
    const errors: string[] = [];
    if (((entity.items.length === 0))) {
      errors.push('Order must have at least one item');
    }
    if (((entity.items.length > 50))) {
      errors.push('Order cannot have more than 50 items');
    }
    if (errors.length > 0) {
      throw new BadRequestException(errors.join('; '));
    }
  }

  async findByCustomerId(customerId: string, skip = 0, take = 100): Promise<Order[]> {
    return this.em.find(
      Order,
      { customerId } as never,
      { limit: take, offset: skip },
    );
  }
  async getByOrderNumber(orderNumber: string): Promise<Order> {
    const entity = await this.em.findOne(Order, {
      orderNumber
    } as never);
    if (!entity) {
      throw new NotFoundException(`Order with orderNumber ${ orderNumber } not found`);
    }
    return entity;
  }
  async findByCustomerIdAndStatus(customerId: string, status: OrderStatus, skip = 0, take = 100): Promise<Order[]> {
    return this.em.find(
      Order,
      { customerId, status } as never,
      { limit: take, offset: skip },
    );
  }
  async findByStatusAndCreatedAt(status: OrderStatus, createdAt: Date, skip = 0, take = 100): Promise<Order[]> {
    return this.em.find(
      Order,
      { status, createdAt } as never,
      { limit: take, offset: skip },
    );
  }

}

import { Injectable, NotFoundException, Logger, ConflictException, BadRequestException } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { OrderCancelledEvent } from '../events/order-cancelled.event';
import { OrderConfirmedEvent } from '../events/order-confirmed.event';
import { OrderCreatedEvent } from '../events/order-created.event';
import { OrderStatus } from '../enums/order-status.enum'
import { OrderStatusChangedEvent } from '../events/order-status-changed.event';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { Order } from '../entities/order.entity';
import { CreateOrderDto } from '../dto/create-order.dto';
import { UpdateOrderDto } from '../dto/update-order.dto';
import { OrderItem } from '../entities/order-item.entity';

@Injectable()
export class OrderService {
  private readonly logger = new Logger(OrderService.name);

  constructor(
    @InjectRepository(Order)
    private readonly orderRepository: Repository<Order>,
    private readonly dataSource: DataSource,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(): Promise<Order[]> {
    this.logger.log('Finding all Order');
    return this.orderRepository.find();
  }

  async findOne(id: string): Promise<Order> {
    const entity = await this.orderRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`Order with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateOrderDto): Promise<Order> {
    const entity = this.orderRepository.create(dto);
    this._validate(entity);
    const saved = await this.orderRepository.save(entity);
this.eventEmitter.emit('OrderCreated', new OrderCreatedEvent({ orderId: saved.id, orderNumber: saved.orderNumber, customerId: saved.customerId, total: saved.total, reservationId: saved.inventoryReservationId }));
    return saved;
  }

  async update(id: string, dto: UpdateOrderDto): Promise<Order> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
    Object.assign(entity, dto);
    this._validate(entity);
    const updated = await this.orderRepository.save(entity);
if (this._fieldChanged(updated, "status", oldValues)) {
  this.eventEmitter.emit('OrderStatusChanged', new OrderStatusChangedEvent({ orderId: updated.id, oldStatus: this._fieldOldValue(updated, "status", oldValues) as OrderStatus, newStatus: updated.status }));
  if ((updated.status === OrderStatus.Confirmed)) {
    const orderItems: Record<string, unknown>[] = items.map((i) => ({productId: i.productId, quantity: i.quantity}));
    const estimatedWeight: number = (items.length * 1.0);
    this.eventEmitter.emit('OrderConfirmed', new OrderConfirmedEvent({ orderId: updated.id, paymentId: updated.paymentId, reservationId: updated.inventoryReservationId, shippingAddress: updated.shippingAddress, items: orderItems, estimatedWeight: estimatedWeight }));
  } else if ((updated.status === OrderStatus.Cancelled)) {
    this.eventEmitter.emit('OrderCancelled', new OrderCancelledEvent({ orderId: updated.id, reason: (updated.cancellationReason ?? 'Cancelled'), reservationId: updated.inventoryReservationId }));
  }
}
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const orderItemCount = await this.dataSource
      .getRepository(OrderItem)
      .count({ where: { orderId: id } as any });
    if (orderItemCount > 0) {
      throw new ConflictException(
        `Cannot delete Order '${id}': ` +
        `${ orderItemCount } items still reference it. ` +
        `Delete or reassign OrderItem records first.`,
      );
    }
    await this.orderRepository.remove(entity);
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
    return this.orderRepository.find({ where: { customerId } as any, skip, take });
  }
  async getByOrderNumber(orderNumber: string): Promise<Order> {
    const entity = await this.orderRepository.findOne({ where: { orderNumber } as any });
    if (!entity) {
      throw new NotFoundException(`Order with orderNumber ${ orderNumber } not found`);
    }
    return entity;
  }
  async findByCustomerIdAndStatus(customerId: string, status: OrderStatus, skip = 0, take = 100): Promise<Order[]> {
    return this.orderRepository.find({
      where: { customerId, status } as any,
      skip,
      take,
    });
  }
  async findByStatusAndCreatedAt(status: OrderStatus, createdAt: Date, skip = 0, take = 100): Promise<Order[]> {
    return this.orderRepository.find({
      where: { status, createdAt } as any,
      skip,
      take,
    });
  }

}

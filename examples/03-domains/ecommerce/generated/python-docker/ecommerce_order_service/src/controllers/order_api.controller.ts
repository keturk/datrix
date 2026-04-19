import {
  Controller,
  Get,
  Post,
  Put,
  Param,
  Query,
  DefaultValuePipe,
  ParseIntPipe,
  Body,
  Req,
  HttpCode,
  HttpStatus,
  ParseUUIDPipe,
  UseGuards,
} from '@nestjs/common';
import { Request } from 'express';
import { AuthGuard } from '../auth/auth.guard';
import { Public } from '../auth/public.decorator';
import { InternalGuard } from '../auth/internal.guard';
import { DataSource, EntityManager } from 'typeorm';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { OrderService } from '../services/order.service';
import { OrderItemService } from '../services/order_item.service';
import { CancelOrderRequest } from '../dto/cancel-order-request.struct';
import { ConfirmPaymentRequest } from '../dto/confirm-payment-request.struct';
import { CreateOrderRequest } from '../dto/create-order-request.struct';
import { NotFoundException } from '@nestjs/common';
import { OrderStatus } from '../enums/order-status.enum';
import { PaginatedOrders } from '../dto/paginated-orders.struct';
import { UpdateShipmentRequest } from '../dto/update-shipment-request.struct';
import { generateOrderNumber } from '../functions';
import { randomUUID } from 'crypto';
import { Order } from '../entities/order.entity';
import { OrderItem } from '../entities/order-item.entity';
import axios from 'axios';
import { BadRequestException, ForbiddenException, UnauthorizedException } from '@nestjs/common';

@UseGuards(AuthGuard)
@Controller('api/v1/orders')
export class OrderAPIController {
  constructor(
    private readonly orderService: OrderService,
    private readonly orderItemService: OrderItemService,
    @InjectRepository(Order) private readonly orderRepository: Repository<Order>,
    @InjectRepository(OrderItem) private readonly orderItemRepository: Repository<OrderItem>,
    private readonly dbDataSource: DataSource,
  ) {}

  @Get('')
  async getEndpoint(
    @Query('page') page?: number,
    @Query('perPage') perPage?: number,
    @Query('status') status?: OrderStatus | null,
    @Req() req: Request,
  ): Promise<PaginatedOrders> {
    const customerId: string = (req as any).user.id;
    let query: Record<string, unknown> = await this.orderRepository.createQueryBuilder('order').where('order.customerId = :customerId', { customerId: customerId }).getOne();
    if ((status != null)) {
      query = query.where(status, status);
    }
    const total: number = query.count();
    const cappedPerPage: number = Math.min(perPage, MAX_PAGE_SIZE);
    const orders: Order[] = query.orderBy(createdAt, desc).offset(((page - 1) * cappedPerPage)).limit(cappedPerPage).all();
    return {data: orders, pagination: {currentPage: page, perPage: cappedPerPage, totalItems: total, totalPages: Math.ceil((total / cappedPerPage)), hasNextPage: (page < Math.ceil((total / cappedPerPage))), hasPrevPage: (page > 1)}};
  }

  @Post('')
  @HttpCode(HttpStatus.CREATED)
  async postEndpoint(
    @Body() request: CreateOrderRequest,
    @Req() req: Request,
  ): Promise<Order> {
    const cached: Record<string, unknown> | null = checkIdempotency(request.idempotencyKey, 'create_order');
    if ((cached != null)) {
      return cached;
    }
    const customerId: string = (req as any).user.id;
    const reservationId: string = randomUUID();
    const availability: Record<string, unknown> = (await axios.post(`${String(process.env['SERVICE_ECOMMERCE_PRODUCT_SERVICE_URL'] ?? '').replace(/\/$/, '')}/${String('/internal/check-availability').replace(/^\/+/, '')}`, request.items)).data
    if ((!availability['allAvailable'])) {
      throw new BadRequestException({code: 'INVENTORY_UNAVAILABLE', message: 'Some products are not available', items: availability['items'].filter((!x.available))});
    }
    const reservation: Record<string, unknown> = (await axios.post(`${String(process.env['SERVICE_ECOMMERCE_PRODUCT_SERVICE_URL'] ?? '').replace(/\/$/, '')}/${String('/internal/reserve-inventory').replace(/^\/+/, '')}`, {reservationId: reservationId, items: request.items, ttlSeconds: 600})).data
    if ((!reservation['success'])) {
      throw new BadRequestException({code: 'RESERVATION_FAILED', message: 'Failed to reserve inventory', error: reservation['error']});
    }
    const order = this.orderRepository.create({orderNumber: generateOrderNumber(), customerId: customerId, shippingAddress: request.shippingAddress, billingAddress: (request.billingAddress ?? request.shippingAddress), status: OrderStatus.Pending, inventoryReservationId: reservationId, subtotal: Number(0), tax: Number(0), shippingCost: Number(0), discount: Number(0)});
    await this.orderRepository.save(order);
    for (const item of request.items) {
      const product: Record<string, unknown> = (await axios.get(`${String(process.env['SERVICE_ECOMMERCE_PRODUCT_SERVICE_URL'] ?? '').replace(/\/$/, '')}/${String(`internal/${item.productId}`).replace(/^\/+/, '')}`)).data
      const entity = this.orderItemRepository.create({order: order, productId: item.productId, productName: product['name'], quantity: item.quantity, unitPrice: product['price']});
      await this.orderItemRepository.save(entity);
    }
    order.calculateTotals();
    await this.orderRepository.save(order);
    storeIdempotency(request.idempotencyKey, 'create_order', order.id, order);
    return order;
  }

  @Get(':id')
  async getEndpoint2(
    @Param('id', ParseUUIDPipe) id: string,
    @Req() req: Request,
  ): Promise<Order> {
    const order = await this.orderRepository.findOneOrFail({ where: { id: id } });
    if (((order.customerId !== (req as any).user.id) && (!((req as any).user?.roles ?? []).includes('admin')))) {
      throw new ForbiddenException('Access denied');
    }
    return order;
  }

  @Put(':id/cancel')
  async putCancel(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() request: CancelOrderRequest,
    @Req() req: Request,
  ): Promise<Order> {
    const order = await this.orderRepository.findOneOrFail({ where: { id: id } });
    if (((order.customerId !== (req as any).user.id) && (!((req as any).user?.roles ?? []).includes('admin')))) {
      throw new ForbiddenException('Cannot cancel another user\'s order');
    }
    if ((!order.canCancel)) {
      throw new BadRequestException({code: 'ORDER_NOT_CANCELLABLE', message: `Order cannot be cancelled in status: ${order.status}`});
    }
    await this.dbDataSource.transaction(async (manager: EntityManager) => {
      order.status = OrderStatus.Cancelled;
      order.cancellationReason = (request.reason ?? 'Cancelled by customer');
      await this.orderRepository.save(order);
    });
    return order;
  }

  @UseGuards(InternalGuard)
  @Post(':id/confirm-payment')
  @HttpCode(HttpStatus.CREATED)
  async postConfirmPayment(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() request: ConfirmPaymentRequest,
  ): Promise<Order> {
    const order = await this.orderRepository.findOneOrFail({ where: { id: id } });
    order.paymentId = request.paymentId;
    order.status = OrderStatus.Confirmed;
    await this.orderRepository.save(order);
    return order;
  }

  @UseGuards(InternalGuard)
  @Post(':id/update-shipment')
  @HttpCode(HttpStatus.CREATED)
  async postUpdateShipment(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() request: UpdateShipmentRequest,
  ): Promise<Order> {
    const order = await this.orderRepository.findOneOrFail({ where: { id: id } });
    order.shipmentId = request.shipmentId;
    await this.orderRepository.save(order);
    return order;
  }

  @UseGuards(InternalGuard)
  @Get('internal/:id')
  async getInternal(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Order> {
    return this.orderService.findOne(id);
  }

  @Get('orders/:id/order_items')
  async listOrderItems(
    @Param('id', ParseUUIDPipe) id: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('take', new DefaultValuePipe(20), ParseIntPipe) take: number,
  ): Promise<OrderItem[]> {
    await this.orderService.findOne(id);
    return this.orderItemService.getByOrder(id, skip, take);
  }

}

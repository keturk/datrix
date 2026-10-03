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
import type { Request } from 'express';
import { AuthGuard } from '../auth/auth.guard';
import { RateLimitGuard } from '../rate-limit/rate-limit.guard';
import { PrincipalTypes } from '../auth/optional-auth.decorator';
import { Providers } from '../auth/providers.decorator';
import { CoerceStringEnumPipe } from '../pipes/string-enum-query.pipe';
import { EntityManager } from '@mikro-orm/core';
import { InjectRepository } from '@mikro-orm/nestjs';
import { EntityRepository } from '@mikro-orm/core';
import { FunctionsService } from '../functions';
import { OrderService } from '../services/order.service';
import { CancelOrderRequest } from '../dto/cancel-order-request.struct';
import { ConfirmPaymentRequest } from '../dto/confirm-payment-request.struct';
import { CreateOrderRequest } from '../dto/create-order-request.struct';
import { Currency } from '../enums/currency.enum';
import { OrderStatus } from '../enums/order-status.enum';
import { PaginatedOrders } from '../dto/paginated-orders.struct';
import { UpdateShipmentRequest } from '../dto/update-shipment-request.struct';
import { Order } from '../ecommerce_order_service/entities/order_db/order.entity';
import { OrderItem } from '../ecommerce_order_service/entities/order_db/order-item.entity';
import axios from 'axios';
import { BadRequestException } from '@nestjs/common';
import { ForbiddenException } from '@nestjs/common';
import { NotFoundException } from '@nestjs/common';
import { UnauthorizedException } from '@nestjs/common';
import { MAX_PAGE_SIZE } from '../constants';
import { ProductServiceAvailabilityResponseResponse } from '../clients/product-service-responses';
import { ProductServiceProductResponse } from '../clients/product-service-responses';
import { ProductServiceReservationResponseResponse } from '../clients/product-service-responses';
import { SqlEntityManager } from '@mikro-orm/postgresql';
import { bufferEvents } from '../eventOutbox';
import { generateOrderNumber } from '../functions';
import { randomUUID } from 'crypto';
import { ApiExtraModels, ApiResponse, ApiExcludeEndpoint, ApiBearerAuth, ApiSecurity } from '@nestjs/swagger';

@ApiExtraModels(CancelOrderRequest, ConfirmPaymentRequest, CreateOrderRequest, PaginatedOrders, UpdateShipmentRequest)
@UseGuards(AuthGuard, RateLimitGuard)
@Controller('api/v1/orders')
export class OrderAPIController {
  constructor(
    private readonly functionsService: FunctionsService,
    private readonly orderService: OrderService,
    @InjectRepository(Order) private readonly orderRepository: EntityRepository<Order>,
    @InjectRepository(OrderItem) private readonly orderItemRepository: EntityRepository<OrderItem>,
    private readonly orderDbEm: EntityManager,
  ) {}

  // Paginated list endpoint with optional filtering
  @Providers('identity', 'customerKeys', 'test_auth')
  @PrincipalTypes('human')
  @ApiBearerAuth()
  @ApiSecurity("customerKeys")
  @Get('')
  @ApiResponse({ status: 200, type: PaginatedOrders })
  async getEndpoint(
    @Req() req: Request,
    @Query('page', new DefaultValuePipe(1), ParseIntPipe) page: number,
    @Query('per_page', new DefaultValuePipe(20), ParseIntPipe) perPage: number,
    @Query('status', new CoerceStringEnumPipe(OrderStatus, true)) status?: OrderStatus,
  ): Promise<PaginatedOrders> {
    let customerId: string = (() => { const p = req.user ?? (() => { throw new UnauthorizedException({ type: 'about:blank', title: 'Unauthorized', status: 401 }); })(); return { ...p, id: p.userId }; })().id;
    let query = (this.orderRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Order, 'e_order').select('*').where('e_order.customer_id = ?', [customerId]);
    if ((status != null)) {
      query = query.where('e_order.status = ?', [status]);
    }
    let total: number = await query.getCount();
    let cappedPerPage: number = Math.min(perPage, MAX_PAGE_SIZE);
    let orders: Order[] = await query.orderBy({ 'e_order.created_at': 'DESC' }).offset(((page - 1) * cappedPerPage)).limit(cappedPerPage).getResultList();
    return Object.assign(new PaginatedOrders(), { data: orders, pagination: {currentPage: page, perPage: cappedPerPage, totalItems: total, totalPages: Math.ceil((total / cappedPerPage)), hasNextPage: (page < Math.ceil((total / cappedPerPage))), hasPrevPage: (page > 1)} });
  }

  @Providers('identity', 'test_auth')
  @PrincipalTypes('human')
  @ApiBearerAuth()
  @Post('')
  @HttpCode(HttpStatus.CREATED)
  async postEndpoint(
    @Body() body: CreateOrderRequest,
    @Req() req: Request,
  ): Promise<Order> {
    // Check idempotency to prevent duplicate orders on retry
    let cached: Record<string, any> | null = await this.functionsService.checkIdempotency(body.idempotencyKey, 'create_order');
    if ((cached != null)) {
      return cached as any;
    }
    let customerId: string = (() => { const p = req.user ?? (() => { throw new UnauthorizedException({ type: 'about:blank', title: 'Unauthorized', status: 401 }); })(); return { ...p, id: p.userId }; })().id;
    let reservationId: string = randomUUID();
    // Cross-service call('config/service.dcfg') : check product availability via ProductService
    let availability: ProductServiceAvailabilityResponseResponse = (await axios.post(`${String(process.env['SERVICE_ECOMMERCE_PRODUCT_SERVICE_URL'] ?? '').replace(/\/$/, '')}/${String('/api/v1/products/service/check-availability').replace(/^\/+/, '')}`, body.items)).data;
    if ((!availability['allAvailable'])) {
      throw new BadRequestException({code: 'INVENTORY_UNAVAILABLE', message: 'Some products are not available', items: availability['items'].filter((x: any) => (!x.available))});
    }
    // Cross-service call('config/service.dcfg') : reserve inventory
    let reservation: ProductServiceReservationResponseResponse = (await axios.post(`${String(process.env['SERVICE_ECOMMERCE_PRODUCT_SERVICE_URL'] ?? '').replace(/\/$/, '')}/${String('/api/v1/products/service/reserve-inventory').replace(/^\/+/, '')}`, {reservationId: reservationId, items: body.items, ttlSeconds: 600})).data;
    if ((!reservation['success'])) {
      throw new BadRequestException({code: 'RESERVATION_FAILED', message: 'Failed to reserve inventory', error: reservation['error']});
    }
    const order = this.orderRepository.create({ orderNumber: await generateOrderNumber(), customerId: customerId, shippingAddress: body.shippingAddress, billingAddress: (body.billingAddress ?? body.shippingAddress), status: OrderStatus.Pending, inventoryReservationId: reservationId, subtotal: Number(0), tax: Number(0), shippingCost: Number(0), discount: Number(0) } as never);
    await this.orderRepository.getEntityManager().persistAndFlush(order);
    for (const item of body.items) {
      // Fetch product details from ProductService for denormalization
      let product: ProductServiceProductResponse = (await axios.get(`${String(process.env['SERVICE_ECOMMERCE_PRODUCT_SERVICE_URL'] ?? '').replace(/\/$/, '')}/${String(`/api/v1/products/service/${item.productId}`).replace(/^\/+/, '')}`)).data;
      const entity = this.orderItemRepository.create({ order: order, productId: item.productId, productName: product['name'], quantity: item.quantity, unitPrice: product['price'] } as never);
      await this.orderItemRepository.getEntityManager().persistAndFlush(entity);
    }
    order.calculateTotals();
    await this.orderRepository.getEntityManager().persistAndFlush(order);
    await this.functionsService.storeIdempotency(body.idempotencyKey, 'create_order', order.id, order);
    return order;
  }

  @Providers('platform', 'test_auth')
  @PrincipalTypes('machine')
  @ApiExcludeEndpoint()
  @ApiBearerAuth()
  @Get('service/:id')
  async getServiceById(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Order> {
    const result = await this.orderRepository.findOne({ id: id });
    if (!result) {
      throw new NotFoundException("Not found");
    }
    return result
  }

  @Providers('platform', 'test_auth')
  @PrincipalTypes('machine')
  @ApiExcludeEndpoint()
  @ApiBearerAuth()
  @Post(':id/confirm-payment')
  @HttpCode(HttpStatus.CREATED)
  async postByIdConfirmPayment(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: ConfirmPaymentRequest,
  ): Promise<Order> {
    let order = await this.orderRepository.findOne({ id: id });
    if (!order) {
      throw new NotFoundException("Not found");
    }
    order.paymentId = body.paymentId;
    order.status = OrderStatus.Confirmed;
    await this.orderRepository.getEntityManager().persistAndFlush(order);
    return order;
  }

  @Providers('platform', 'test_auth')
  @PrincipalTypes('machine')
  @ApiExcludeEndpoint()
  @ApiBearerAuth()
  @Post(':id/update-shipment')
  @HttpCode(HttpStatus.CREATED)
  async postByIdUpdateShipment(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: UpdateShipmentRequest,
  ): Promise<Order> {
    let order = await this.orderRepository.findOne({ id: id });
    if (!order) {
      throw new NotFoundException("Not found");
    }
    order.shipmentId = body.shipmentId;
    await this.orderRepository.getEntityManager().persistAndFlush(order);
    return order;
  }

  @Providers('identity', 'test_auth')
  @PrincipalTypes('human')
  @ApiBearerAuth()
  @Put(':id/cancel')
  async putByIdCancel(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: CancelOrderRequest,
    @Req() req: Request,
  ): Promise<Order> {
    let order = await this.orderRepository.findOne({ id: id });
    if (!order) {
      throw new NotFoundException("Not found");
    }
    if (((order.customerId !== (() => { const p = req.user ?? (() => { throw new UnauthorizedException({ type: 'about:blank', title: 'Unauthorized', status: 401 }); })(); return { ...p, id: p.userId }; })().id) && (!(req.user?.roles ?? []).includes('admin')))) {
      throw new ForbiddenException('Cannot cancel another user\'s order');
    }
    if ((!order.canCancel)) {
      throw new BadRequestException({code: 'ORDER_NOT_CANCELLABLE', message: `Order cannot be cancelled in status: ${order.status}`});
    }
    await bufferEvents(async () => {
      await this.orderDbEm.transactional(async (manager: EntityManager) => {
      order.status = OrderStatus.Cancelled;
      order.cancellationReason = (body.reason ?? 'Cancelled by customer');
      await this.orderRepository.getEntityManager().persistAndFlush(order);
    });
    });
    return order;
  }

  @Providers('identity', 'test_auth')
  @PrincipalTypes('human')
  @ApiBearerAuth()
  @Get(':id')
  async getById(
    @Param('id', ParseUUIDPipe) id: string,
    @Req() req: Request,
  ): Promise<Order> {
    let order = await this.orderRepository.findOne({ id: id });
    if (!order) {
      throw new NotFoundException("Not found");
    }
    if (((order.customerId !== (() => { const p = req.user ?? (() => { throw new UnauthorizedException({ type: 'about:blank', title: 'Unauthorized', status: 401 }); })(); return { ...p, id: p.userId }; })().id) && (!(req.user?.roles ?? []).includes('admin')))) {
      throw new ForbiddenException('Access denied');
    }
    return order;
  }

}

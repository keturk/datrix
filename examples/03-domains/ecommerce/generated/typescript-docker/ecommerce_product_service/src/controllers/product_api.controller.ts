import {
  Controller,
  Delete,
  Get,
  Patch,
  Post,
  Put,
  Param,
  Query,
  DefaultValuePipe,
  ParseIntPipe,
  Body,
  HttpCode,
  HttpStatus,
  ParseUUIDPipe,
  UseGuards,
} from '@nestjs/common';
import { AuthGuard } from '../auth/auth.guard';
import { Public } from '../auth/public.decorator';
import { InternalGuard } from '../auth/internal.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { RequiredPipe } from '../pipes/required.pipe';
import { EntityManager } from '@mikro-orm/core';
import { InjectRepository } from '@mikro-orm/nestjs';
import { EntityRepository } from '@mikro-orm/core';
import { ProductService } from '../services/product.service';
import { AvailabilityItem } from '../dto/availability-item.struct';
import { AvailabilityResponse } from '../dto/availability-response.struct';
import { BulkProductRequest } from '../dto/bulk-product-request.struct';
import { CheckAvailabilityRequest } from '../dto/check-availability-request.struct';
import { ConfirmReservationRequest } from '../dto/confirm-reservation-request.struct';
import { CreateProductRequest } from '../dto/create-product-request.struct';
import { ProductStatus } from '../enums/product-status.enum';
import { ReleaseReservationRequest } from '../dto/release-reservation-request.struct';
import { ReservationResponse } from '../dto/reservation-response.struct';
import { ReservationStatus } from '../enums/reservation-status.enum';
import { ReserveInventoryRequest } from '../dto/reserve-inventory-request.struct';
import { UpdateInventoryRequest } from '../dto/update-inventory-request.struct';
import { UpdateProductDto } from '../dto/update-product.dto';
import { InventoryReservation } from '../ecommerce_product_service/entities/product_db/inventory-reservation.entity';
import { Product } from '../ecommerce_product_service/entities/product_db/product.entity';
import { BadRequestException } from '@nestjs/common';
import { NotFoundException } from '@nestjs/common';
import { SqlEntityManager } from '@mikro-orm/postgresql';
import { _getRedis } from '../ecommerce_product_service/_cacheHelpers';
import { addSeconds } from 'date-fns';
import { bufferEvents } from '../eventOutbox';
import { producerInstance as mqProducerInstance } from '../mq/producer';
import { ApiExtraModels, ApiResponse, ApiExcludeEndpoint } from '@nestjs/swagger';

@ApiExtraModels(AvailabilityItem, AvailabilityResponse, BulkProductRequest, CheckAvailabilityRequest, ConfirmReservationRequest, CreateProductRequest, ReleaseReservationRequest, ReservationResponse, ReserveInventoryRequest, UpdateInventoryRequest)
@UseGuards(AuthGuard)
@Controller('api/v1/products')
export class ProductAPIController {
  constructor(
    private readonly productService: ProductService,
    @InjectRepository(InventoryReservation) private readonly inventoryReservationRepository: EntityRepository<InventoryReservation>,
    @InjectRepository(Product) private readonly productRepository: EntityRepository<Product>,
    private readonly productDbEm: EntityManager,
  ) {}

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Post('')
  @HttpCode(HttpStatus.CREATED)
  async postEndpoint(
    @Body() body: CreateProductRequest,
  ): Promise<Product> {
    const product = this.productRepository.create({ name: body.name, description: body.description, price: body.price, category: body.categoryId, inventory: body.inventory, status: ProductStatus.Draft, images: [], tags: [] } as never);
    await this.productRepository.getEntityManager().persistAndFlush(product);
    // Call trait method to generate URL slug
    product.slug = body.name.toLowerCase().trim().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
    await this.productRepository.getEntityManager().persistAndFlush(product);
    if (mqProducerInstance !== null) {
      await mqProducerInstance.publishProductCreated({ productId: product.id, name: product.name, price: product.price });
    }
    return product;
  }

  @Public()
  @Get('')
  async listProducts(
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
  ): Promise<Product[]> {
    return this.productService.findAll(skip, limit);
  }

  // Full-text search endpoint
  @Public()
  @Get('search')
  async getSearch(
    @Query('query', RequiredPipe) query: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit') limit: number | null = null,
    @Query('offset') offset: number | null = null,
  ): Promise<Product[]> {
    return this.productService.findAll(skip, limit);
  }

  // 'whereIn(...)' filters by a set of values
  @Public()
  @UseGuards(InternalGuard)
  @ApiExcludeEndpoint()
  @Post('service/bulk')
  @HttpCode(HttpStatus.CREATED)
  async postServiceBulk(
    @Body() body: BulkProductRequest,
  ): Promise<Product[]> {
    return await (this.productRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Product, 'e_product').select('*').where({ id: { $in: body.ids } }).getResultList();
  }

  // Internal endpoints for cross-service communication
  @Public()
  @UseGuards(InternalGuard)
  @ApiExcludeEndpoint()
  @Post('service/check-availability')
  @HttpCode(HttpStatus.CREATED)
  @ApiResponse({ status: 201, type: AvailabilityResponse })
  async postServiceCheckAvailability(
    @Body() body: CheckAvailabilityRequest,
  ): Promise<AvailabilityResponse> {
    let availability: AvailabilityItem[] = [];
    let allAvailable: boolean = true;
    for (const item of body.items) {
      let product: Product | null = await this.productRepository.findOne({ id: item.productId });
      if (!product) throw new NotFoundException('product not found');
      if (((product == null) || (product.inventory < item.quantity))) {
        allAvailable = false;
        availability.push({productId: item.productId, available: false, availableQuantity: (product?.inventory ?? 0)});
      } else {
        availability.push({productId: item.productId, available: true, availableQuantity: product.inventory});
      }
    }
    return Object.assign(new AvailabilityResponse(), { allAvailable: allAvailable, items: availability });
  }

  @Public()
  @UseGuards(InternalGuard)
  @ApiExcludeEndpoint()
  @Post('service/confirm-reservation')
  @HttpCode(HttpStatus.CREATED)
  async postServiceConfirmReservation(
    @Body() body: ConfirmReservationRequest,
  ): Promise<void> {
    let reservations: InventoryReservation[] = await (this.inventoryReservationRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(InventoryReservation, 'e_inventory_reservation').select('*').where('e_inventory_reservation.reservation_id = ?', [body.reservationId]).andWhere('e_inventory_reservation.status = ?', [ReservationStatus.Reserved]).getResultList();
    for (const reservation of reservations) {
      reservation.status = ReservationStatus.Confirmed;
      await this.inventoryReservationRepository.getEntityManager().persistAndFlush(reservation);
    }
    console.info('inventory_reservation_confirmed');
  }

  @Public()
  @UseGuards(InternalGuard)
  @ApiExcludeEndpoint()
  @Post('service/release-reservation')
  @HttpCode(HttpStatus.CREATED)
  async postServiceReleaseReservation(
    @Body() body: ReleaseReservationRequest,
  ): Promise<void> {
    let reservations: InventoryReservation[] = await (this.inventoryReservationRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(InventoryReservation, 'e_inventory_reservation').select('*').where('e_inventory_reservation.reservation_id = ?', [body.reservationId]).andWhere('e_inventory_reservation.status = ?', [ReservationStatus.Reserved]).getResultList();
    await bufferEvents(async () => {
      await this.productDbEm.transactional(async (manager: EntityManager) => {
      for (const reservation of reservations) {
        let product: Product | null = await this.productRepository.findOne({ id: reservation.product.id });
        if (!product) throw new NotFoundException('product not found');
        if ((product != null)) {
          product.inventory = (product.inventory + reservation.quantity);
          await this.productRepository.getEntityManager().persistAndFlush(product);
        }
        reservation.status = ReservationStatus.Released;
        await this.inventoryReservationRepository.getEntityManager().persistAndFlush(reservation);
      }
    });
    });
    if (mqProducerInstance !== null) {
      await mqProducerInstance.publishInventoryReleased({ reservationId: body.reservationId, reason: 'Released by request' });
    }
    console.info('inventory_reservation_released');
  }

  @Public()
  @UseGuards(InternalGuard)
  @ApiExcludeEndpoint()
  @Post('service/reserve-inventory')
  @HttpCode(HttpStatus.CREATED)
  @ApiResponse({ status: 201, type: ReservationResponse })
  async postServiceReserveInventory(
    @Body() body: ReserveInventoryRequest,
  ): Promise<ReservationResponse> {
    await bufferEvents(async () => {
      await this.productDbEm.transactional(async (manager: EntityManager) => {
      for (const item of body.items) {
        const product = await this.productRepository.findOne({ id: item.productId });
    if (!product) {
      throw new NotFoundException("Not found");
    }
        if ((product.inventory < item.quantity)) {
          throw new BadRequestException({code: 'INSUFFICIENT_INVENTORY', productId: item.productId, requested: item.quantity, available: product.inventory});
        }
        product.inventory = (product.inventory - item.quantity);
        await this.productRepository.getEntityManager().persistAndFlush(product);
        const entity = this.inventoryReservationRepository.create({ reservationId: body.reservationId, product: item.productId, quantity: item.quantity, expiresAt: addSeconds(new Date(), body.ttlSeconds), status: ReservationStatus.Reserved } as never);
        await this.inventoryReservationRepository.getEntityManager().persistAndFlush(entity);
      }
    });
    });
    // Lambda expression: '.map(i => i.productId)'
    let productIds: string[] = body.items.map((i) => i.productId);
    if (mqProducerInstance !== null) {
      await mqProducerInstance.publishInventoryReserved({ reservationId: body.reservationId, productIds: productIds });
    }
    return Object.assign(new ReservationResponse(), { success: true, reservationId: body.reservationId ?? null });
  }

  @Public()
  @Get('category/:categoryId')
  async getCategoryByCategoryId(
    @Param('categoryId', ParseUUIDPipe) categoryId: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit') limit: number | null = null,
  ): Promise<Product[]> {
    return await (this.productRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Product, 'e_product').select('*').where('e_product.category_id = ?', [categoryId]).where('e_product.status = ?', [ProductStatus.Active]).orderBy({ 'e_product.name': 'ASC' }).limit((limit ?? 50)).getResultList();
  }

  @Public()
  @UseGuards(InternalGuard)
  @ApiExcludeEndpoint()
  @Get('service/:id')
  async getServiceById(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Product> {
    return this.productService.findOne(id);
  }

  @Public()
  @Get('slug/:slug')
  async getSlugBySlug(
    @Param('slug') slug: string,
  ): Promise<Product> {
    let cached = (await (async () => {
      const _m = await _getRedis().hgetall((String("product:") + ':' + String(`slug:${slug}`)));
      const out: Record<string, any> = {};
      for (const [k, v] of Object.entries(_m)) {
        out[k] = JSON.parse(String(v));
      }
      return out;
    })());
    if ((cached != null)) {
      return cached as any;
    }
    const product = await (this.productRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Product, 'e_product').select('*').where('e_product.slug = ?', [slug]).getSingleResult();
    if (!product) {
      throw new NotFoundException("Not found");
    }
    (await Promise.all([_getRedis().hset((String("product:") + ':' + String(product.id)), Object.fromEntries(Object.entries(product).map(([k, v]) => [String(k), JSON.stringify(v)]))), _getRedis().expire((String("product:") + ':' + String(product.id)), 3600)]))[0];
    return product;
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Patch(':id/inventory')
  async putByIdInventory(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: UpdateInventoryRequest,
  ): Promise<Product> {
    const product = await this.productRepository.findOne({ id: id });
    if (!product) {
      throw new NotFoundException("Not found");
    }
    let oldInventory: number = product.inventory;
    product.inventory = body.inventory;
    await this.productRepository.getEntityManager().persistAndFlush(product);
    if (mqProducerInstance !== null) {
      await mqProducerInstance.publishInventoryUpdated({ productId: product.id, oldQuantity: oldInventory, newQuantity: body.inventory });
    }
    return product;
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Put(':id/publish')
  async putByIdPublish(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Product> {
    const product = await this.productRepository.findOne({ id: id });
    if (!product) {
      throw new NotFoundException("Not found");
    }
    product.publish();
    return product;
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async deleteProduct(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<void> {
    let entity: Product | null = await this.productRepository.findOne({ id: id });
    if (!entity) throw new NotFoundException('entity not found');
    await this.productRepository.getEntityManager().removeAndFlush(entity);
  }

  @Public()
  @Get(':id')
  async getProduct(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Product> {
    return this.productService.findOne(id);
  }

  // Creation is not a plain resource verb here: the explicit post(...) below
  // claims POST /api/v1/products so it can generate the slug and dispatch
  // ProductCreated. Listing 'create' as well would give one route two
  // declarations, and only the first would be reachable.
  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Patch(':id')
  async updateProduct(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: UpdateProductDto,
  ): Promise<Product> {
    let entity: Product | null = await this.productRepository.findOne({ id: id });
    if (!entity) throw new NotFoundException('entity not found');
    Object.assign(entity, body);
    await this.productRepository.getEntityManager().persistAndFlush(entity);
    return entity;
  }

}

import {
  Controller,
  Delete,
  Get,
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
import { EventEmitter2 } from '@nestjs/event-emitter';
import { AuthGuard } from '../auth/auth.guard';
import { Public } from '../auth/public.decorator';
import { InternalGuard } from '../auth/internal.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { DataSource, EntityManager } from 'typeorm';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { ProductService } from '../services/product.service';
import { AvailabilityResponse } from '../dto/availability-response.struct';
import { BulkProductRequest } from '../dto/bulk-product-request.struct';
import { CheckAvailabilityRequest } from '../dto/check-availability-request.struct';
import { ConfirmReservationRequest } from '../dto/confirm-reservation-request.struct';
import { CreateProductRequest } from '../dto/create-product-request.struct';
import { InventoryReleasedEvent } from '../events/inventory-released.event';
import { InventoryReservedEvent } from '../events/inventory-reserved.event';
import { InventoryUpdatedEvent } from '../events/inventory-updated.event';
import { NotFoundException } from '@nestjs/common';
import { ProductCreatedEvent } from '../events/product-created.event';
import { ProductStatus } from '../enums/product-status.enum';
import { ReleaseReservationRequest } from '../dto/release-reservation-request.struct';
import { ReservationResponse } from '../dto/reservation-response.struct';
import { ReservationStatus } from '../enums/reservation-status.enum';
import { ReserveInventoryRequest } from '../dto/reserve-inventory-request.struct';
import { UpdateInventoryRequest } from '../dto/update-inventory-request.struct';
import { _getRedis } from '../ecommerce_product_service/_cacheHelpers';
import { addSeconds } from 'date-fns';
import { InventoryReservation } from '../entities/inventory-reservation.entity';
import { Product } from '../entities/product.entity';
import { BadRequestException, ForbiddenException, UnauthorizedException } from '@nestjs/common';

@UseGuards(AuthGuard)
@Controller('api/v1/products')
export class ProductAPIController {
  constructor(
    private readonly productService: ProductService,
    @InjectRepository(InventoryReservation) private readonly inventoryReservationRepository: Repository<InventoryReservation>,
    @InjectRepository(Product) private readonly productRepository: Repository<Product>,
    private readonly eventEmitter: EventEmitter2,
    private readonly dbDataSource: DataSource,
  ) {}

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Post('')
  @HttpCode(HttpStatus.CREATED)
  async postEndpoint(
    @Body() request: CreateProductRequest,
  ): Promise<Product> {
    const product = this.productRepository.create({name: request.name, description: request.description, price: request.price, categoryId: request.categoryId, inventory: request.inventory, status: ProductStatus.Draft, images: [], tags: []});
    await this.productRepository.save(product);
    product.generateSlug(request.name);
    await this.productRepository.save(product);
    this.eventEmitter.emit('ProductCreated', new ProductCreatedEvent({ productId: product.id, name: product.name, price: product.price }));
    return product;
  }

  @UseGuards(InternalGuard)
  @Post('internal/bulk')
  @HttpCode(HttpStatus.CREATED)
  async postInternalBulk(
    @Body() request: BulkProductRequest,
  ): Promise<Product[]> {
    return await this.productRepository.createQueryBuilder('product').where('product.id IN (:idList)', { idList: request.ids }).getMany();
  }

  @UseGuards(InternalGuard)
  @Post('internal/check-availability')
  @HttpCode(HttpStatus.CREATED)
  async postInternalCheckAvailability(
    @Body() request: CheckAvailabilityRequest,
  ): Promise<AvailabilityResponse> {
    const availability: AvailabilityItem[] = [];
    let allAvailable: boolean = true;
    for (const item of request.items) {
      const product: Product | null = await this.productRepository.findOne({ where: { id: item.productId } });
      if (((product == null) || (product.inventory < item.quantity))) {
        allAvailable = false;
        availability.push({productId: item.productId, available: false, availableQuantity: (product?.inventory ?? 0)});
      } else {
        availability.push({productId: item.productId, available: true, availableQuantity: product.inventory});
      }
    }
    return {allAvailable: allAvailable, items: availability};
  }

  @UseGuards(InternalGuard)
  @Post('internal/confirm-reservation')
  @HttpCode(HttpStatus.CREATED)
  async postInternalConfirmReservation(
    @Body() request: ConfirmReservationRequest,
  ): Promise<void> {
    const reservations: InventoryReservation[] = await this.inventoryReservationRepository.createQueryBuilder('inventoryReservation').where('inventoryReservation.reservationId = :reservationId', { reservationId: request.reservationId }).andWhere('inventoryReservation.status = :status', { status: ReservationStatus.Reserved }).getMany();
    for (const reservation of reservations) {
      reservation.status = ReservationStatus.Confirmed;
      reservation.save();
    }
    console.info('inventory_reservation_confirmed');;
  }

  @UseGuards(InternalGuard)
  @Post('internal/release-reservation')
  @HttpCode(HttpStatus.CREATED)
  async postInternalReleaseReservation(
    @Body() request: ReleaseReservationRequest,
  ): Promise<void> {
    const reservations: InventoryReservation[] = await this.inventoryReservationRepository.createQueryBuilder('inventoryReservation').where('inventoryReservation.reservationId = :reservationId', { reservationId: request.reservationId }).andWhere('inventoryReservation.status = :status', { status: ReservationStatus.Reserved }).getMany();
    await this.dbDataSource.transaction(async (manager: EntityManager) => {
      for (const reservation of reservations) {
        const product: Product | null = await this.productRepository.findOne({ where: { id: reservation.productId } });
        if ((product != null)) {
          product.inventory = (product.inventory + reservation.quantity);
          await this.productRepository.save(product);
        }
        reservation.status = ReservationStatus.Released;
        reservation.save();
      }
    });
    this.eventEmitter.emit('InventoryReleased', new InventoryReleasedEvent({ reservationId: request.reservationId, reason: 'Released by request' }));
    console.info('inventory_reservation_released');;
  }

  @UseGuards(InternalGuard)
  @Post('internal/reserve-inventory')
  @HttpCode(HttpStatus.CREATED)
  async postInternalReserveInventory(
    @Body() request: ReserveInventoryRequest,
  ): Promise<ReservationResponse> {
    await this.dbDataSource.transaction(async (manager: EntityManager) => {
      for (const item of request.items) {
        const product = await this.productRepository.findOneOrFail({ where: { id: item.productId } });
        if ((product.inventory < item.quantity)) {
          throw new BadRequestException({code: 'INSUFFICIENT_INVENTORY', productId: item.productId, requested: item.quantity, available: product.inventory});
        }
        product.inventory = (product.inventory - item.quantity);
        await this.productRepository.save(product);
        const entity = this.inventoryReservationRepository.create({reservationId: request.reservationId, productId: item.productId, quantity: item.quantity, expiresAt: addSeconds(new Date(), request.ttlSeconds), status: ReservationStatus.Reserved});
        await this.inventoryReservationRepository.save(entity);
      }
    });
    const productIds: string[] = request.items.map((i) => i.productId);
    this.eventEmitter.emit('InventoryReserved', new InventoryReservedEvent({ reservationId: request.reservationId, productIds: productIds }));
    return {success: true, reservationId: request.reservationId};
  }

  @Public()
  @Get('products')
  async listProducts(
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
  ): Promise<Product[]> {
    return this.productService.findAll();
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Post('products')
  @HttpCode(HttpStatus.CREATED)
  async createProduct(
    @Body() body: Product,
  ): Promise<Product> {
    return this.productService.create(body);
  }

  @Public()
  @Get('search')
  async getSearch(
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('query') query?: string,
    @Query('limit') limit?: number | null,
    @Query('offset') offset?: number | null,
  ): Promise<Product[]> {
    return this.productService.findAll();
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Put(':id/inventory')
  async putInventory(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() request: UpdateInventoryRequest,
  ): Promise<Product> {
    const product = await this.productRepository.findOneOrFail({ where: { id: id } });
    const oldInventory: number = product.inventory;
    product.inventory = request.inventory;
    await this.productRepository.save(product);
    this.eventEmitter.emit('InventoryUpdated', new InventoryUpdatedEvent({ productId: product.id, oldQuantity: oldInventory, newQuantity: request.inventory }));
    return product;
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Put(':id/publish')
  async putPublish(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Product> {
    const product = await this.productRepository.findOneOrFail({ where: { id: id } });
    product.publish();
    return product;
  }

  @Public()
  @Get('category/:categoryId')
  async getCategory(
    @Param('categoryId', ParseUUIDPipe) categoryId: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit') limit?: number | null,
  ): Promise<Product[]> {
    return await this.productRepository.createQueryBuilder('product').where('product.categoryId = :categoryId', { categoryId: categoryId }).where('product.status = :status', { status: ProductStatus.Active }).orderBy('product.name', 'ASC').take((limit ?? 50)).getMany();
  }

  @UseGuards(InternalGuard)
  @Get('internal/:id')
  async getInternal(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Product> {
    return this.productService.findOne(id);
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Delete('products/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async deleteProduct(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<void> {
    await this.productService.remove(id);
  }

  @Public()
  @Get('products/:id')
  async getProduct(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Product> {
    return this.productService.findOne(id);
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Put('products/:id')
  async updateProduct(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: Product,
  ): Promise<Product> {
    return this.productService.update(id, body);
  }

  @Public()
  @Get('slug/:slug')
  async getSlug(
    @Param('slug') slug: string,
  ): Promise<Product> {
    const cached: Record<string, unknown> | null = (JSON.parse(await _getRedis().get(`productCache:${`slug:${slug}`}`) ?? 'null') as unknown);
    if ((cached != null)) {
      return cached;
    }
    const product = await this.productRepository.createQueryBuilder('product').where('product.slug = :slug', { slug: slug }).getOneOrFail();
    await _getRedis().set(`productCache:${product.id}`, JSON.stringify(product));;
    return product;
  }

}

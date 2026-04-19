import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { InventoryUpdatedEvent } from '../events/inventory-updated.event';
import { ProductStatus } from '../enums/product-status.enum'
import { _getRedis } from '../ecommerce_product_service/_cacheHelpers';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { Product } from '../entities/product.entity';
import { CreateProductDto } from '../dto/create-product.dto';
import { UpdateProductDto } from '../dto/update-product.dto';

@Injectable()
export class ProductService {
  private readonly logger = new Logger(ProductService.name);

  constructor(
    @InjectRepository(Product)
    private readonly productRepository: Repository<Product>,
    private readonly dataSource: DataSource,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(): Promise<Product[]> {
    this.logger.log('Finding all Product');
    return this.productRepository.find();
  }

  async findOne(id: string): Promise<Product> {
    const entity = await this.productRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`Product with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateProductDto): Promise<Product> {
    const entity = this.productRepository.create(dto);
    const saved = await this.productRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateProductDto): Promise<Product> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
    Object.assign(entity, dto);
    const updated = await this.productRepository.save(entity);
if (this._fieldChanged(updated, "inventory", oldValues)) {
  this.eventEmitter.emit('InventoryUpdated', new InventoryUpdatedEvent({ productId: updated.id, oldQuantity: this._fieldOldValue(updated, "inventory", oldValues) as number, newQuantity: updated.inventory }));
}
if (this._fieldChanged(updated, "status", oldValues)) {
  await _getRedis().del(`productCache:${`product:${updated.id}`}`);;
  await _getRedis().del(`productCache:${`product:slug:${updated.slug}`}`);;
}
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.productRepository.remove(entity);
  }

  private _fieldChanged(
    current: Product,
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
    current: Product,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): unknown {
    if (snapshot === undefined) {
      return undefined;
    }
    return snapshot[fieldName];
  }



  async getBySlug(slug: string): Promise<Product> {
    const entity = await this.productRepository.findOne({ where: { slug } as any });
    if (!entity) {
      throw new NotFoundException(`Product with slug ${ slug } not found`);
    }
    return entity;
  }
  async findByCategoryIdAndStatus(categoryId: string, status: ProductStatus, skip = 0, take = 100): Promise<Product[]> {
    return this.productRepository.find({
      where: { categoryId, status } as any,
      skip,
      take,
    });
  }
  async findByStatusAndInventory(status: ProductStatus, inventory: number, skip = 0, take = 100): Promise<Product[]> {
    return this.productRepository.find({
      where: { status, inventory } as any,
      skip,
      take,
    });
  }
  async findByNameAndDescription(name: string, description: string, skip = 0, take = 100): Promise<Product[]> {
    return this.productRepository.find({
      where: { name, description } as any,
      skip,
      take,
    });
  }

  async getByCategory(categoryId: string, skip = 0, take = 100): Promise<Product[]> {
    return this.productRepository.find({ where: { categoryId } as any, skip, take });
  }
}

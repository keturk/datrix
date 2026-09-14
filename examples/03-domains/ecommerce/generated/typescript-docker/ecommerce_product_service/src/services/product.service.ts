import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { ProductStatus } from '../enums/product-status.enum'
import { productDbProductAfterUpdate } from '../hooks/product-db-product-after-update.hook';
import { EntityManager } from '@mikro-orm/core';
import { Product } from '../ecommerce_product_service/entities/product_db/product.entity';
import { CreateProductDto } from '../dto/create-product.dto';
import { UpdateProductDto } from '../dto/update-product.dto';

@Injectable()
export class ProductService {
  private readonly logger = new Logger(ProductService.name);

  constructor(
    private readonly em: EntityManager,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<Product[]> {
    this.logger.log('Finding all Product');
    return this.em.find(
      Product,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<Product> {
    const entity = await this.em.findOne(Product, { id } as never);
    if (!entity) {
      throw new NotFoundException(`Product with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateProductDto): Promise<Product> {
    const entity = this.em.create(Product, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateProductDto): Promise<Product> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
    this.em.assign(entity, dto as never);
    await this.em.flush();
    const updated = entity;
    await productDbProductAfterUpdate(updated, this.em, oldValues);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    await this.em.removeAndFlush(entity);
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



  async getBySlug(slug: string | null): Promise<Product> {
    const entity = await this.em.findOne(Product, {
      slug
    } as never);
    if (!entity) {
      throw new NotFoundException(`Product with slug ${ slug } not found`);
    }
    return entity;
  }
  async findByCategoryId(categoryId: string, skip = 0, take = 100): Promise<Product[]> {
    return this.em.find(
      Product,
      { categoryId } as never,
      { limit: take, offset: skip },
    );
  }
  async findByCategoryIdAndStatus(categoryId: string, status: ProductStatus, skip = 0, take = 100): Promise<Product[]> {
    return this.em.find(
      Product,
      { categoryId, status } as never,
      { limit: take, offset: skip },
    );
  }
  async findByStatusAndInventory(status: ProductStatus, inventory: number, skip = 0, take = 100): Promise<Product[]> {
    return this.em.find(
      Product,
      { status, inventory } as never,
      { limit: take, offset: skip },
    );
  }
  async findByNameAndDescription(name: string, description: string, skip = 0, take = 100): Promise<Product[]> {
    return this.em.find(
      Product,
      { name, description } as never,
      { limit: take, offset: skip },
    );
  }

  async getByCategory(categoryId: string, skip = 0, take = 100): Promise<Product[]> {
    return this.em.find(
      Product,
      { category: categoryId } as never,
      { limit: take, offset: skip },
    );
  }
}

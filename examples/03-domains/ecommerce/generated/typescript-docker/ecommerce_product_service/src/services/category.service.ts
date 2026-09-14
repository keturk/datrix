import { Injectable, NotFoundException, Logger, ConflictException } from '@nestjs/common';
import { EntityManager } from '@mikro-orm/core';
import { Category } from '../ecommerce_product_service/entities/product_db/category.entity';
import { CreateCategoryDto } from '../dto/create-category.dto';
import { UpdateCategoryDto } from '../dto/update-category.dto';
import { Product } from '../ecommerce_product_service/entities/product_db/product.entity';

@Injectable()
export class CategoryService {
  private readonly logger = new Logger(CategoryService.name);

  constructor(
    private readonly em: EntityManager,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<Category[]> {
    this.logger.log('Finding all Category');
    return this.em.find(
      Category,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<Category> {
    const entity = await this.em.findOne(Category, { id } as never);
    if (!entity) {
      throw new NotFoundException(`Category with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateCategoryDto): Promise<Category> {
    const entity = this.em.create(Category, dto as never);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    return saved;
  }

  async update(id: string, dto: UpdateCategoryDto): Promise<Category> {
    const entity = await this.findOne(id);
    this.em.assign(entity, dto as never);
    await this.em.flush();
    const updated = entity;
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const productCount = await this.em.count(Product, {
      category: id,
    } as never);
    if (productCount > 0) {
      throw new ConflictException(
        `Cannot delete Category '${id}': ` +
        `${ productCount } products still reference it. ` +
        `Delete or reassign Product records first.`,
      );
    }
    await this.em.removeAndFlush(entity);
  }




  async getByName(name: string): Promise<Category> {
    const entity = await this.em.findOne(Category, {
      name
    } as never);
    if (!entity) {
      throw new NotFoundException(`Category with name ${ name } not found`);
    }
    return entity;
  }
  async getBySlug(slug: string): Promise<Category> {
    const entity = await this.em.findOne(Category, {
      slug
    } as never);
    if (!entity) {
      throw new NotFoundException(`Category with slug ${ slug } not found`);
    }
    return entity;
  }

}

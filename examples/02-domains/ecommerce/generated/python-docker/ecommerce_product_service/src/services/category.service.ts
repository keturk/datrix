import { Injectable, NotFoundException, Logger, ConflictException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { Category } from '../entities/category.entity';
import { CreateCategoryDto } from '../dto/create-category.dto';
import { UpdateCategoryDto } from '../dto/update-category.dto';
import { Product } from '../entities/product.entity';

@Injectable()
export class CategoryService {
  private readonly logger = new Logger(CategoryService.name);

  constructor(
    @InjectRepository(Category)
    private readonly categoryRepository: Repository<Category>,
    private readonly dataSource: DataSource,
  ) {}

  async findAll(): Promise<Category[]> {
    this.logger.log('Finding all Category');
    return this.categoryRepository.find();
  }

  async findOne(id: string): Promise<Category> {
    const entity = await this.categoryRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`Category with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateCategoryDto): Promise<Category> {
    const entity = this.categoryRepository.create(dto);
    const saved = await this.categoryRepository.save(entity);
    return saved;
  }

  async update(id: string, dto: UpdateCategoryDto): Promise<Category> {
    const entity = await this.findOne(id);
    Object.assign(entity, dto);
    const updated = await this.categoryRepository.save(entity);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const productCount = await this.dataSource
      .getRepository(Product)
      .count({ where: { categoryId: id } as any });
    if (productCount > 0) {
      throw new ConflictException(
        `Cannot delete Category '${id}': ` +
        `${ productCount } products still reference it. ` +
        `Delete or reassign Product records first.`,
      );
    }
    await this.categoryRepository.remove(entity);
  }




  async getByName(name: string): Promise<Category> {
    const entity = await this.categoryRepository.findOne({ where: { name } as any });
    if (!entity) {
      throw new NotFoundException(`Category with name ${ name } not found`);
    }
    return entity;
  }
  async getBySlug(slug: string): Promise<Category> {
    const entity = await this.categoryRepository.findOne({ where: { slug } as any });
    if (!entity) {
      throw new NotFoundException(`Category with slug ${ slug } not found`);
    }
    return entity;
  }

}

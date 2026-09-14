import {
  Entity,
  Property,
  Enum,
  ManyToOne,
  Index,
  OptionalProps,
  wrap,
} from '@mikro-orm/core';

import type { EventEmitter2 } from '@nestjs/event-emitter';
import { _fieldChanged, _fieldOldValue } from '../../../entity-hook-helpers';

import { Category } from './category.entity';
import { ProductStatus } from '../../../enums/product-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index({ name: 'idx_products_category_id', properties: ['category'] })
@Index({ name: 'idx_products_category_id_status', properties: ['category', 'status'] })
@Index({ name: 'idx_products_status_inventory', properties: ['status', 'inventory'] })
@Entity({ tableName: 'products' })
export class Product extends BaseEntity {
  [OptionalProps]?: "compareAtPrice" | "createdAt" | "discountPercent" | "eventEmitter" | "id" | "inventory" | "isAvailable" | "price" | "productMetadata" | "slug" | "status" | "updatedAt";

  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('@mikro-orm/core').EntityManager;

  @Property({ columnType: 'varchar', nullable: true, unique: true })
  slug!: string | null;

  @Property({ columnType: 'decimal' })
  price!: number;

  @Property({ columnType: 'decimal', fieldName: 'compare_at_price', nullable: true })
  compareAtPrice!: number | null;

  @Property({ columnType: 'int', default: 0 })
  inventory!: number;

  @Property({ columnType: 'varchar' })
  name!: string;

  @Property({ columnType: 'text' })
  description!: string;

  @Enum({ items: () => ProductStatus, nativeEnumName: 'product_status' })
  status!: ProductStatus;

  @Property({ columnType: 'jsonb', type: 'json', fieldName: 'product_metadata', nullable: true })
  productMetadata!: Record<string, any> | null;

  @Property({ columnType: 'jsonb', type: 'json' })
  images!: Record<string, any>;

  @Property({ columnType: 'jsonb', type: 'json' })
  tags!: Record<string, any>;


  @ManyToOne({ entity: () => Category, inversedBy: 'products', deleteRule: 'restrict', fieldName: 'category_id' })
  category!: Category;

  get isAvailable(): boolean {
    return ((this.status === ProductStatus.Active) && this.hasStock());
  }
  get discountPercent(): number {
    return this.getDiscountPercent();
  }

  /** Persist pending entity changes via the associated EntityManager. */
  async save(): Promise<void> {
    await wrap(this, true).__em!.flush();
  }

  hasDiscount(): boolean {
    return ((this.compareAtPrice != null) && (this.compareAtPrice > this.price!));
  }

  getDiscountPercent(): number {
    if ((!this.hasDiscount())) {
      return 0;
    }
    return (((this.compareAtPrice!- this.price!) / this.compareAtPrice!) * 100);
  }

  reserveInventory(quantity: number): boolean {
    if ((this.inventory >= quantity)) {
      this.inventory = (this.inventory!- quantity);
      return true;
    }
    return false;
  }

  releaseInventory(quantity: number): void {
    this.inventory = (this.inventory!+ quantity);
  }

  hasStock(): boolean {
    return (this.inventory > 0);
  }

  async publish(): Promise<void> {
    if ((this.status === ProductStatus.Draft)) {
      this.status = ProductStatus.Active;
      await this.save();
    }
  }

  async discontinue(): Promise<void> {
    this.status = ProductStatus.Discontinued;
    await this.save();
  }


}

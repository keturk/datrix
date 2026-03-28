import {
  Entity,
  Column,
  ManyToOne,
  JoinColumn,
  Index,
  BeforeInsert,
  BeforeUpdate,
  BeforeRemove,
  AfterInsert,
  AfterUpdate,
  AfterRemove,
  AfterLoad,
} from 'typeorm';

import type { EventEmitter2 } from '@nestjs/event-emitter';
import { InventoryUpdatedEvent } from '../events/inventory-updated.event';
import { _fieldChanged, _fieldOldValue } from '../entity-hook-helpers';
import { _getRedis } from '../ecommerce_product_service/_cacheHelpers';

import { Category } from './category.entity';
import { ProductStatus } from '../enums/product-status.enum';
import { BaseEntity } from './base-entity.entity';

@Index('idx_products_category_id_status', ['categoryId', 'status'])
@Index('idx_products_status_inventory', ['status', 'inventory'])
@Entity('products')
export class Product extends BaseEntity {
  /** Injected by generated lifecycle subscriber before persistence; not a DB column. */
  eventEmitter!: EventEmitter2;
  /** Snapshot before update for ``isChanged`` / ``oldValue``; not a DB column. */
  __datrixOldValues?: Record<string, unknown>;
  /** EntityManager injected by lifecycle subscriber for hook repository access; not a DB column. */
  __datrixEntityManager?: import('typeorm').EntityManager;

  @Column({
    type: 'varchar',
    unique: true,
  })
  slug!: string;

  @Column({
    type: 'decimal',
  })
  price!: number;

  @Column({
    type: 'decimal',
    nullable: true,
  })
  compareAtPrice?: number | null;

  @Column({
    type: 'int',
    default: 0,
  })
  inventory!: number;

  @Column({
    type: 'varchar',
  })
  name!: string;

  @Column({
    type: 'text',
  })
  description!: string;

  @Column({
    type: 'enum',
    default: ProductStatus.Draft,
    enum: ProductStatus,
  })
  status!: ProductStatus;

  @Column({
    type: 'jsonb',
    nullable: true,
  })
  productMetadata?: Record<string, unknown> | null;

  @Column({
    type: 'jsonb',
  })
  images!: Record<string, unknown>;

  @Column({
    type: 'jsonb',
  })
  tags!: Record<string, unknown>;


  @ManyToOne(() => Category, (category) => category.products, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'category_id' })
  category!: Category;
  categoryId!: string;

  isAvailable!: boolean;
  discountPercent!: number;

  @AfterLoad()
  _hydrateComputed(): void {
    this.isAvailable = ((this.status === ProductStatus.Active) && this.hasStock());
    this.discountPercent = this.getDiscountPercent();
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

  publish(): void {
    if ((this.status === ProductStatus.Draft)) {
      this.status = ProductStatus.Active;
      this.save();
    }
  }

  discontinue(): void {
    this.status = ProductStatus.Discontinued;
    this.save();
  }


  @AfterUpdate()
  async _hookafterUpdate(): Promise<void> {
    if (_fieldChanged(this, "inventory", this.__datrixOldValues!)) {
      this.eventEmitter.emit('InventoryUpdated', new InventoryUpdatedEvent({ productId: this.id, oldQuantity: _fieldOldValue(this, "inventory", this.__datrixOldValues!) as number, newQuantity: this.inventory }));
    }
    if (_fieldChanged(this, "status", this.__datrixOldValues!)) {
      await _getRedis().del(`productCache:${`product:${this.id}`}`);;
      await _getRedis().del(`productCache:${`product:slug:${this.slug}`}`);;
    }
  }

}

import {
  Entity,
  Property,
  OneToMany,
  Collection,
  OptionalProps,
} from '@mikro-orm/core';


import { Product } from './product.entity';
import { BaseEntity } from './base-entity.entity';

@Entity({ tableName: 'categories' })
export class Category extends BaseEntity {
  [OptionalProps]?: "createdAt" | "description" | "id" | "updatedAt";


  @Property({ columnType: 'varchar', unique: true })
  name!: string;

  @Property({ columnType: 'text', nullable: true })
  description!: string | null;

  @Property({ columnType: 'varchar', unique: true })
  slug!: string;


  @OneToMany({ entity: () => Product, mappedBy: 'category' })
  products = new Collection<Product>(this);



}

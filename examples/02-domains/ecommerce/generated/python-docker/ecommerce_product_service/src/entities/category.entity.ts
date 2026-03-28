import {
  Entity,
  Column,
  OneToMany,
} from 'typeorm';


import { Product } from './product.entity';
import { BaseEntity } from './base-entity.entity';

@Entity('categories')
export class Category extends BaseEntity {

  @Column({
    type: 'varchar',
    unique: true,
  })
  name!: string;

  @Column({
    type: 'text',
    nullable: true,
  })
  description?: string | null;

  @Column({
    type: 'varchar',
    unique: true,
  })
  slug!: string;


  @OneToMany(() => Product, (product) => product.category)
  products!: Product[];



}

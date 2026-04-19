import {
  BaseEntity as TypeOrmBaseEntity,
  Column,
  PrimaryGeneratedColumn,
} from 'typeorm';

import { randomUUID } from 'crypto';


export abstract class BaseEntity extends TypeOrmBaseEntity {

  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({
    type: 'timestamp',
    default: new Date(),
  })
  createdAt!: Date;

  @Column({
    type: 'timestamp',
    default: new Date(),
  })
  updatedAt!: Date;





}

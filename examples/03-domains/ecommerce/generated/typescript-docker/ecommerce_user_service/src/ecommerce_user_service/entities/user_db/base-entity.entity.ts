import {
  Entity,
  Property,
  PrimaryKey,
} from '@mikro-orm/core';



@Entity({ abstract: true })
export abstract class BaseEntity {

  @Property({ columnType: 'timestamptz', fieldName: 'created_at', defaultRaw: 'CURRENT_TIMESTAMP' })
  createdAt!: Date;

  @Property({ onCreate: () => new Date(), onUpdate: () => new Date(), fieldName: 'updated_at' })
  updatedAt!: Date;

  @PrimaryKey({ columnType: 'uuid', defaultRaw: 'gen_random_uuid()' })
  id!: string;





}

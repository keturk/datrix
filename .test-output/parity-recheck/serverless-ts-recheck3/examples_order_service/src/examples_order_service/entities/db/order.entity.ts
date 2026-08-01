import {
  Entity,
  Property,
  PrimaryKey,
  OptionalProps,
} from '@mikro-orm/core';



@Entity({ tableName: 'orders' })
export class Order {
  [OptionalProps]?: "id";


  @PrimaryKey({ columnType: 'uuid', defaultRaw: 'gen_random_uuid()' })
  id!: string;

  @Property({ columnType: 'decimal' })
  amount!: number;

  @Property({ columnType: 'varchar' })
  currency!: string;

  @Property({ columnType: 'varchar' })
  status!: string;





}

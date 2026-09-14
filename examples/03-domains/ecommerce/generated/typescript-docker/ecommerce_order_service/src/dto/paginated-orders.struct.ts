import {
  IsArray,
  IsObject,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Order } from '../ecommerce_order_service/entities/order_db/order.entity'

export class PaginatedOrders {

  @ApiProperty()
  @IsArray()
  data!: Order[];

  @ApiProperty()
  @IsObject()
  pagination!: Record<string, any>;


}

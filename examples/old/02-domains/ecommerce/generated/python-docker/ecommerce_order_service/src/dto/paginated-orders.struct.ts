import {
  IsArray,
  IsObject,
} from 'class-validator';
import { Order } from '../entities/order.entity'

export class PaginatedOrders {

  @IsArray()
  data!: Order[];

  @IsObject()
  pagination!: Record<string, unknown>;


}

import {
  IsArray,
  IsInt,
  IsUUID,
} from 'class-validator';
import { OrderLineInput } from '../dto/order-line-input.struct'

export class ReserveInventoryRequest {

  @IsUUID()
  reservationId!: string;

  @IsArray()
  items!: OrderLineInput[];

  @IsInt()
  ttlSeconds!: number;


}

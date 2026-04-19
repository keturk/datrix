import {
  IsArray,
} from 'class-validator';
import { OrderLineInput } from '../dto/order-line-input.struct'

export class CheckAvailabilityRequest {

  @IsArray()
  items!: OrderLineInput[];


}

import {
  IsArray,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { OrderLineInput } from '../dto/order-line-input.struct'

export class CheckAvailabilityRequest {

  // Array<Type> defines a collection field
  @ApiProperty()
  @IsArray()
  items!: OrderLineInput[];


}

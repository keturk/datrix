import {
  IsArray,
  ValidateNested,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { OrderLineInput } from '../dto/order-line-input.struct'

export class CheckAvailabilityRequest {

  // Array<Type> defines a collection field
  @ApiProperty()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => OrderLineInput)
  items!: OrderLineInput[];


}

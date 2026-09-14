import {
  IsArray,
  IsInt,
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { OrderLineInput } from '../dto/order-line-input.struct'

export class ReserveInventoryRequest {

  @ApiProperty()
  @IsUUID()
  reservationId!: string;

  @ApiProperty()
  @IsArray()
  items!: OrderLineInput[];

  @ApiProperty()
  @IsInt()
  ttlSeconds!: number;


}

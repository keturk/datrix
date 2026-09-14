import {
  IsInt,
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class OrderLineInput {

  @ApiProperty()
  @IsUUID()
  productId!: string;

  @ApiProperty()
  @IsInt()
  quantity!: number;


}

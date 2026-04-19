import {
  IsInt,
  IsUUID,
} from 'class-validator';

export class OrderLineInput {

  @IsUUID()
  productId!: string;

  @IsInt()
  quantity!: number;


}

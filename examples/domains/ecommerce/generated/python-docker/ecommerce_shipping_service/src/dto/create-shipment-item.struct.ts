import {
  IsInt,
  IsUUID,
} from 'class-validator';

export class CreateShipmentItem {

  @IsUUID()
  productId!: string;

  @IsInt()
  quantity!: number;


}

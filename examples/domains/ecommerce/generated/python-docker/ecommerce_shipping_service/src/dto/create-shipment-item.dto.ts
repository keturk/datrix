
import {
  IsDate,
  IsInt,
  IsOptional,
  IsUUID,
} from 'class-validator';
import { Type } from 'class-transformer';

export class CreateShipmentItemDto {

  @IsUUID()
  productId!: string;

  @IsInt()
  quantity!: number;

  @IsUUID()
  shipmentId!: string;
}

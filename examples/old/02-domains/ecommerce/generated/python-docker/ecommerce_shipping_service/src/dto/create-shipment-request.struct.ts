import {
  IsArray,
  IsNumber,
  IsObject,
  IsUUID,
} from 'class-validator';
import { Address } from '../dto/address.struct'
import { CreateShipmentItem } from '../dto/create-shipment-item.struct'

export class CreateShipmentRequest {

  @IsUUID()
  orderId!: string;

  @IsObject()
  destination!: Address;

  @IsArray()
  items!: CreateShipmentItem[];

  @IsNumber()
  weight!: number;


}

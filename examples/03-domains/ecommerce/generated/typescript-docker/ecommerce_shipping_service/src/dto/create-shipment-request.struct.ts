import {
  IsArray,
  IsNumber,
  IsObject,
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Address } from '../dto/address.struct'
import { CreateShipmentItem } from '../dto/create-shipment-item.struct'

export class CreateShipmentRequest {

  @ApiProperty()
  @IsUUID()
  orderId!: string;

  @ApiProperty()
  @IsObject()
  destination!: Address;

  @ApiProperty()
  @IsArray()
  items!: CreateShipmentItem[];

  @ApiProperty()
  @IsNumber()
  weight!: number;


}

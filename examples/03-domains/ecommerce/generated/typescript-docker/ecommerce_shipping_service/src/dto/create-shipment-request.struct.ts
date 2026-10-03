import {
  IsArray,
  IsNumber,
  IsObject,
  IsUUID,
  ValidateNested,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { Address } from '../dto/address.struct'
import { CreateShipmentItem } from '../dto/create-shipment-item.struct'

export class CreateShipmentRequest {

  @ApiProperty()
  @IsUUID()
  orderId!: string;

  @ApiProperty()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  destination!: Address;

  @ApiProperty()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => CreateShipmentItem)
  items!: CreateShipmentItem[];

  @ApiProperty()
  @IsNumber()
  weight!: number;


}

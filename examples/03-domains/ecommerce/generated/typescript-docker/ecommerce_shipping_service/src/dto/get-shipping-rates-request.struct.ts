import {
  IsNumber,
  IsObject,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Address } from '../dto/address.struct'

export class GetShippingRatesRequest {

  @ApiProperty()
  @IsObject()
  destination!: Address;

  @ApiProperty()
  @IsNumber()
  weight!: number;


}

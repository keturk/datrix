import {
  IsNumber,
  IsObject,
  ValidateNested,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { Address } from '../dto/address.struct'

export class GetShippingRatesRequest {

  @ApiProperty()
  @IsObject()
  @ValidateNested()
  @Type(() => Address)
  destination!: Address;

  @ApiProperty()
  @IsNumber()
  weight!: number;


}

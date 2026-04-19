import {
  IsNumber,
  IsObject,
} from 'class-validator';
import { Address } from '../dto/address.struct'

export class GetShippingRatesRequest {

  @IsObject()
  destination!: Address;

  @IsNumber()
  weight!: number;


}

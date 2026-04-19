import {
  IsEnum,
  IsInt,
  IsNumber,
} from 'class-validator';
import { ShippingCarrier } from '../enums/shipping-carrier.enum'

export class ShippingRateResponse {

  @IsEnum(ShippingCarrier)
  carrier!: ShippingCarrier;

  @IsNumber()
  rate!: number;

  @IsInt()
  estimatedDays!: number;


}

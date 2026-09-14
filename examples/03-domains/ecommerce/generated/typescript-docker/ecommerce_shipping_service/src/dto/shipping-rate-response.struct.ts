import {
  IsEnum,
  IsInt,
  IsNumber,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { ShippingCarrier } from '../enums/shipping-carrier.enum'

export class ShippingRateResponse {

  @ApiProperty({ enum: ShippingCarrier, enumName: 'ShippingCarrier' })
  @IsEnum(ShippingCarrier)
  carrier!: ShippingCarrier;

  @ApiProperty()
  @IsNumber()
  rate!: number;

  @ApiProperty()
  @IsInt()
  estimatedDays!: number;


}

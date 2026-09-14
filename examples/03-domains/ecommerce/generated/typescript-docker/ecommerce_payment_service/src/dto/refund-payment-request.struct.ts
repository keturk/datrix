import {
  IsNotEmpty,
  IsNumber,
  IsString,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class RefundPaymentRequest {

  @ApiProperty()
  @IsNumber({ maxDecimalPlaces: 4 })
  amount!: number;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  reason!: string;


}

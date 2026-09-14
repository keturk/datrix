import {
  IsBoolean,
  IsInt,
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class AvailabilityItem {

  @ApiProperty()
  @IsUUID()
  productId!: string;

  @ApiProperty()
  @IsBoolean()
  available!: boolean;

  @ApiProperty()
  @IsInt()
  availableQuantity!: number;


}


import {
  IsDefined,
  IsInt,
  IsOptional,
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';

export class CreateShipmentItemDto {

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  productId!: string;

  @ApiProperty()
  @IsDefined()
  @IsInt()
  quantity!: number;

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  shipmentId!: string;
}

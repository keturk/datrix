import {
  IsArray,
  IsInt,
  IsUUID,
  ValidateIf,
  ValidateNested,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { OrderLineInput } from '../dto/order-line-input.struct'

export class ReserveInventoryRequest {

  @ApiProperty()
  @IsUUID()
  reservationId!: string;

  @ApiProperty()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => OrderLineInput)
  items!: OrderLineInput[];

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsInt()
  ttlSeconds: number = 600;


}

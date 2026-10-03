import {
  IsArray,
  IsBoolean,
  ValidateNested,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { AvailabilityItem } from '../dto/availability-item.struct'

export class AvailabilityResponse {

  @ApiProperty()
  @IsBoolean()
  allAvailable!: boolean;

  @ApiProperty()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => AvailabilityItem)
  items!: AvailabilityItem[];


}

import {
  IsArray,
  IsBoolean,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { AvailabilityItem } from '../dto/availability-item.struct'

export class AvailabilityResponse {

  @ApiProperty()
  @IsBoolean()
  allAvailable!: boolean;

  @ApiProperty()
  @IsArray()
  items!: AvailabilityItem[];


}

import {
  IsArray,
  IsBoolean,
} from 'class-validator';
import { AvailabilityItem } from '../dto/availability-item.struct'

export class AvailabilityResponse {

  @IsBoolean()
  allAvailable!: boolean;

  @IsArray()
  items!: AvailabilityItem[];


}

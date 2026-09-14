import {
  IsInt,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class UpdateInventoryRequest {

  @ApiProperty()
  @IsInt()
  inventory!: number;


}

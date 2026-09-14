import {
  IsArray,
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class BulkProductRequest {

  @ApiProperty()
  @IsArray()
  @IsUUID(undefined, { each: true })
  ids!: string[];


}

import {
  IsArray,
  IsUUID,
} from 'class-validator';

export class BulkProductRequest {

  @IsArray()
  @IsUUID(undefined, { each: true })
  ids!: string[];


}

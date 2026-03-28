import {
  IsInt,
} from 'class-validator';

export class UpdateInventoryRequest {

  @IsInt()
  inventory!: number;


}

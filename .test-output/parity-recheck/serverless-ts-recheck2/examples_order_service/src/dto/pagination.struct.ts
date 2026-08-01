import {
  IsInt,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class Pagination {

  @IsInt()
  page!: number;

  @IsInt()
  perPage!: number;

  get offset(): number {
    return ((this.page!- 1) * this.perPage!);
  }

}

import {
  IsInt,
} from 'class-validator';

export class Pagination {

  @IsInt()
  page!: number;

  @IsInt()
  perPage!: number;

  get offset(): number {
    return ((this.page!- 1) * this.perPage!);
  }

}

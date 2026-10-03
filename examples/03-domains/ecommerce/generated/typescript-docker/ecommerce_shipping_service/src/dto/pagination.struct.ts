import {
  IsInt,
  ValidateIf,
} from 'class-validator';
import { ApiPropertyOptional } from '@nestjs/swagger';

export class Pagination {

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsInt()
  page: number = 1;

  @ApiPropertyOptional()
  @ValidateIf((_object, value) => value !== undefined)
  @IsInt()
  perPage: number = 20;

  get offset(): number {
    return ((this.page!- 1) * this.perPage!);
  }

}

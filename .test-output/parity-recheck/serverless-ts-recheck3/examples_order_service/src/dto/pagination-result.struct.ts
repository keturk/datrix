import {
  IsBoolean,
  IsInt,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class PaginationResult {

  @IsInt()
  page!: number;

  @IsInt()
  perPage!: number;

  @IsInt()
  total!: number;

  @IsInt()
  totalPages!: number;

  @IsBoolean()
  hasNext!: boolean;

  @IsBoolean()
  hasPrev!: boolean;


}

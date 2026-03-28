import { ProductStatus } from '../enums/product-status.enum';

export class ProductResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  slug!: string;
  price!: number;
  compareAtPrice?: number | null;
  inventory!: number;
  name!: string;
  description!: string;
  status!: ProductStatus;
  productMetadata?: Record<string, unknown> | null;
  images!: Record<string, unknown>;
  tags!: Record<string, unknown>;
  categoryId!: string;

  isAvailable!: boolean;
  discountPercent!: number;
}

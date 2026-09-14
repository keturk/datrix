import { ProductStatus } from '../enums/product-status.enum';

export class ProductResponseDto {
  createdAt!: Date;
  updatedAt!: Date;
  id!: string;
  slug?: string | null;
  price!: number;
  compareAtPrice?: number | null;
  inventory!: number;
  name!: string;
  description!: string;
  status!: ProductStatus;
  productMetadata?: Record<string, any> | null;
  images!: Record<string, any>;
  tags!: Record<string, any>;
  categoryId!: string;

  isAvailable!: boolean;
  discountPercent!: number;
}

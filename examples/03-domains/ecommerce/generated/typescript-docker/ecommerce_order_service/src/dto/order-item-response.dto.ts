
export class OrderItemResponseDto {
  createdAt!: Date;
  updatedAt!: Date;
  id!: string;
  productId!: string;
  productName!: string;
  quantity!: number;
  unitPrice!: number;
  orderId!: string;

  total!: number;
}

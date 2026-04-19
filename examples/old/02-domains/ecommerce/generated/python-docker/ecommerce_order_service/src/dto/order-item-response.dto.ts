
export class OrderItemResponseDto {
  id!: string;
  createdAt!: Date;
  updatedAt!: Date;
  productId!: string;
  productName!: string;
  quantity!: number;
  unitPrice!: number;
  orderId!: string;

  total!: number;
}

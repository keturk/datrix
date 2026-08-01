import {
  Controller,
  Get,
  Param,
  Query,
  DefaultValuePipe,
  ParseIntPipe,
  HttpCode,
  HttpStatus,
  ParseUUIDPipe,
} from '@nestjs/common';
import { Public } from '../auth/public.decorator';
import { OrderService } from '../services/order.service';
import { Order } from '../examples_order_service/entities/db/order.entity';

@Controller('api/v1')
export class OrderApiController {
  constructor(
    private readonly orderService: OrderService,
  ) {}

  @Public()
  @Get('orders')
  async listOrders(
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
  ): Promise<Order[]> {
    return this.orderService.findAll(skip, limit);
  }

  @Public()
  @Get('orders/:id')
  async getOrder(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Order> {
    return this.orderService.findOne(id);
  }

}

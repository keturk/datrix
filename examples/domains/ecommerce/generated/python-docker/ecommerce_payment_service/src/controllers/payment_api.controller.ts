import {
  Controller,
  Get,
  Post,
  Param,
  Query,
  DefaultValuePipe,
  ParseIntPipe,
  Body,
  Req,
  HttpCode,
  HttpStatus,
  ParseUUIDPipe,
  UseGuards,
} from '@nestjs/common';
import { Request } from 'express';
import { AuthGuard } from '../auth/auth.guard';
import { Public } from '../auth/public.decorator';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { PaymentService } from '../services/payment.service';
import { RefundService } from '../services/refund.service';
import { NotFoundException } from '@nestjs/common';
import { PaymentStatus } from '../enums/payment-status.enum';
import { ProcessPaymentRequest } from '../dto/process-payment-request.struct';
import { RefundPaymentRequest } from '../dto/refund-payment-request.struct';
import { StripeWebhookRequest } from '../dto/stripe-webhook-request.struct';
import { processPaymentAsync } from 'ecommerce-payment-service/functions';
import { Payment } from '../entities/payment.entity';
import { Refund } from '../entities/refund.entity';
import { BadRequestException, ForbiddenException, UnauthorizedException } from '@nestjs/common';

@UseGuards(AuthGuard)
@Controller('api/v1/payments')
export class PaymentAPIController {
  constructor(
    private readonly paymentService: PaymentService,
    private readonly refundService: RefundService,
    @InjectRepository(Payment) private readonly paymentRepository: Repository<Payment>,
    @InjectRepository(Refund) private readonly refundRepository: Repository<Refund>,
  ) {}

  @Get('my-payments')
  async getMyPayments(
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
    @Query('page') page?: number,
    @Query('perPage') perPage?: number,
  ): Promise<Payment[]> {
    return this.paymentService.findAll();
  }

  @Post('process')
  @HttpCode(HttpStatus.CREATED)
  async postProcess(
    @Body() request: ProcessPaymentRequest,
    @Req() req: Request,
  ): Promise<Payment> {
    const customerId: string = (req as any).user.id;
    const payment = this.paymentRepository.create({orderId: request.orderId, customerId: customerId, amount: request.amount, method: request.method, transactionId: generateTransactionId(), status: PaymentStatus.Pending});
    await this.paymentRepository.save(payment);
    processPaymentAsync(payment, request.cardToken);
    return payment;
  }

  @Public()
  @Post('webhook/stripe')
  @HttpCode(HttpStatus.CREATED)
  async postWebhookStripe(
    @Body() request: StripeWebhookRequest,
  ): Promise<void> {
    const eventType: string = request.payload.type;
    const data: Record<string, unknown> = request.payload.data.object;
    if ((eventType === 'payment_intent.succeeded')) {
      const transactionId: string = data.metadata.transactionId;
      const payment: Payment | null = await this.paymentRepository.createQueryBuilder('payment').where('payment.transactionId = :transactionId', { transactionId: transactionId }).getOne();
      if (((payment != null) && (payment.status === PaymentStatus.Processing))) {
        payment.status = PaymentStatus.Completed;
        payment.processedAt = new Date();
        payment.gatewayResponse = JSON.stringify(data);
        await this.paymentRepository.save(payment);
      }
    } else if ((eventType === 'payment_intent.payment_failed')) {
      const transactionId: string = data.metadata.transactionId;
      const payment: Payment | null = await this.paymentRepository.createQueryBuilder('payment').where('payment.transactionId = :transactionId', { transactionId: transactionId }).getOne();
      if (((payment != null) && (payment.status === PaymentStatus.Processing))) {
        payment.status = PaymentStatus.Failed;
        payment.errorMessage = (data.lastPaymentError?.message ?? 'Payment failed');
        payment.gatewayResponse = JSON.stringify(data);
        await this.paymentRepository.save(payment);
      }
    }
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Post(':id/refund')
  @HttpCode(HttpStatus.CREATED)
  async postRefund(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() request: RefundPaymentRequest,
  ): Promise<Refund> {
    const payment = await this.paymentRepository.findOneOrFail({ where: { id: id } });
    if ((!payment.canRefund)) {
      throw new BadRequestException(`Cannot refund payment in status: ${payment.status}`);
    }
    let totalRefunded: number = Number(0);
    for (const refund of payment.refunds) {
      if (refund.isSuccessful) {
        totalRefunded = (totalRefunded + refund.amount);
      }
    }
    if (((totalRefunded + request.amount).amount > payment.amount.amount)) {
      throw new BadRequestException('Refund amount exceeds original payment');
    }
    const refund = this.refundRepository.create({payment: payment, amount: request.amount, reason: request.reason, status: PaymentStatus.Pending});
    await this.refundRepository.save(refund);
    const success: boolean = processRefundViaGateway(payment, refund);
    if (success) {
      refund.status = PaymentStatus.Completed;
      refund.processedAt = new Date();
      await this.refundRepository.save(refund);
      const newTotalRefunded: number = (totalRefunded + request.amount);
      if ((newTotalRefunded.amount >= payment.amount.amount)) {
        payment.status = PaymentStatus.Refunded;
        await this.paymentRepository.save(payment);
      }
    } else {
      refund.status = PaymentStatus.Failed;
      await this.refundRepository.save(refund);
    }
    return refund;
  }

  @Get('order/:orderId')
  async getOrder(
    @Param('orderId', ParseUUIDPipe) orderId: string,
  ): Promise<Payment> {
    return this.paymentService.findOne(orderId);
  }

  @Get('payments/:id')
  async getPayment(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Payment> {
    return this.paymentService.findOne(id);
  }

  @Get('payments/:id/refunds')
  async listPaymentRefunds(
    @Param('id', ParseUUIDPipe) id: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('take', new DefaultValuePipe(20), ParseIntPipe) take: number,
  ): Promise<Refund[]> {
    await this.paymentService.findOne(id);
    return this.refundService.getByPayment(id, skip, take);
  }

}

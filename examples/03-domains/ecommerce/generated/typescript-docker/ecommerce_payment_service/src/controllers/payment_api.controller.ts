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
import type { Request } from 'express';
import { AuthGuard } from '../auth/auth.guard';
import { Public } from '../auth/public.decorator';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { WebhookVerify, WebhookVerifyGuard } from '../auth/webhook-verify.guard';
import { InjectRepository } from '@mikro-orm/nestjs';
import { EntityRepository } from '@mikro-orm/core';
import { FunctionsService } from '../functions';
import { PaymentService } from '../services/payment.service';
import { RefundService } from '../services/refund.service';
import { Currency } from '../enums/currency.enum';
import { PaymentStatus } from '../enums/payment-status.enum';
import { ProcessPaymentRequest } from '../dto/process-payment-request.struct';
import { RefundPaymentRequest } from '../dto/refund-payment-request.struct';
import { StripeWebhookRequest } from '../dto/stripe-webhook-request.struct';
import { Payment } from '../ecommerce_payment_service/entities/payment_db/payment.entity';
import { Refund } from '../ecommerce_payment_service/entities/payment_db/refund.entity';
import { BadRequestException } from '@nestjs/common';
import { NotFoundException } from '@nestjs/common';
import { MAX_PAGE_SIZE } from '../constants';
import { SqlEntityManager } from '@mikro-orm/postgresql';
import { generateTransactionId } from '../functions';
import { processRefundViaGateway } from '../functions';
import { ApiExtraModels } from '@nestjs/swagger';

@ApiExtraModels(ProcessPaymentRequest, RefundPaymentRequest, StripeWebhookRequest)
@UseGuards(AuthGuard)
@Controller('api/v1/payments')
export class PaymentAPIController {
  constructor(
    private readonly functionsService: FunctionsService,
    private readonly paymentService: PaymentService,
    private readonly refundService: RefundService,
    @InjectRepository(Payment) private readonly paymentRepository: EntityRepository<Payment>,
    @InjectRepository(Refund) private readonly refundRepository: EntityRepository<Refund>,
  ) {}

  @Get('my-payments')
  async getMyPayments(
    @Req() req: Request,
    @Query('page', new DefaultValuePipe(1), ParseIntPipe) page: number,
    @Query('per_page', new DefaultValuePipe(20), ParseIntPipe) perPage: number,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
  ): Promise<Payment[]> {
    let customerId: string = ((u) => (u == null ? u : { ...u, id: u.id ?? u.sub }))((req as any).user).id;
    let cappedPerPage: number = Math.min(perPage, MAX_PAGE_SIZE);
    return await (this.paymentRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Payment, 'e_payment').select('*').where('e_payment.customer_id = ?', [customerId]).orderBy({ 'e_payment.created_at': 'DESC' }).offset(((page - 1) * cappedPerPage)).limit(cappedPerPage).getResultList();
  }

  @Post('process')
  @HttpCode(HttpStatus.CREATED)
  async postProcess(
    @Body() body: ProcessPaymentRequest,
    @Req() req: Request,
  ): Promise<Payment> {
    let customerId: string = ((u) => (u == null ? u : { ...u, id: u.id ?? u.sub }))((req as any).user).id;
    const payment = this.paymentRepository.create({ orderId: body.orderId, customerId: customerId, amount: body.amount, method: body.method, transactionId: await generateTransactionId(), status: PaymentStatus.Pending } as never);
    await this.paymentRepository.getEntityManager().persistAndFlush(payment);
    // Delegate to async processing function
    await this.functionsService.processPaymentAsync(payment, body.cardToken);
    return payment;
  }

  // Inbound payment-gateway callback. The sender is an external machine,
  // so the endpoint carries no user auth — authenticity comes from the
  // gateway's payload signature, verified against a logical secret handle
  // declared in config/payment-service.dcfg before the body is trusted.
  @Public()
  @UseGuards(new WebhookVerifyGuard({"algorithm": "sha256", "elementSeparator": ",", "headerLayout": "keyed-list", "mode": "signature", "secretEnvVar": "PAYMENT_WEBHOOK_SECRET", "signatureHeader": "Stripe-Signature", "signatureKey": "v1", "signedPayloadTemplate": "{timestamp}.{body}", "timestampKey": "t", "timestampSource": "signature-header", "toleranceSeconds": 300}))
  @WebhookVerify({"algorithm": "sha256", "elementSeparator": ",", "headerLayout": "keyed-list", "mode": "signature", "secretEnvVar": "PAYMENT_WEBHOOK_SECRET", "signatureHeader": "Stripe-Signature", "signatureKey": "v1", "signedPayloadTemplate": "{timestamp}.{body}", "timestampKey": "t", "timestampSource": "signature-header", "toleranceSeconds": 300})
  @Post('webhook/stripe')
  @HttpCode(HttpStatus.CREATED)
  async postWebhookStripe(
    @Body() body: StripeWebhookRequest,
  ): Promise<void> {
    let eventType: string = body.payload.type;
    let data: Record<string, any> = body.payload.data.object;
    if ((eventType === 'payment_intent.succeeded')) {
      let transactionId: string = data.metadata.transactionId;
      let payment: Payment | null = (await (this.paymentRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Payment, 'e_payment').select('*').where('e_payment.transaction_id = ?', [transactionId]).limit(1).getResultList())[0] ?? null;
      if (((payment != null) && (payment.status === PaymentStatus.Processing))) {
        payment.status = PaymentStatus.Completed;
        payment.processedAt = new Date();
        payment.gatewayResponse = JSON.stringify(data);
        await this.paymentRepository.getEntityManager().persistAndFlush(payment);
      }
    } else if ((eventType === 'payment_intent.payment_failed')) {
      let transactionId: string = data.metadata.transactionId;
      let payment: Payment | null = (await (this.paymentRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Payment, 'e_payment').select('*').where('e_payment.transaction_id = ?', [transactionId]).limit(1).getResultList())[0] ?? null;
      if (((payment != null) && (payment.status === PaymentStatus.Processing))) {
        payment.status = PaymentStatus.Failed;
        payment.errorMessage = (data.lastPaymentError?.message ?? 'Payment failed');
        payment.gatewayResponse = JSON.stringify(data);
        await this.paymentRepository.getEntityManager().persistAndFlush(payment);
      }
    }
  }

  @Get('order/:orderId')
  async getOrderByOrderId(
    @Param('orderId', ParseUUIDPipe) orderId: string,
  ): Promise<Payment> {
    const result = await (this.paymentRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(Payment, 'e_payment').select('*').where('e_payment.order_id = ?', [orderId]).getSingleResult();
    if (!result) {
      throw new NotFoundException("Not found");
    }
    return result
  }

  @Get(':id/refunds')
  async listPaymentRefunds(
    @Param('id', ParseUUIDPipe) id: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
  ): Promise<Refund[]> {
    await this.paymentService.findOne(id);
    return this.refundService.getByPayment(id, skip, limit);
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Post(':id/refund')
  @HttpCode(HttpStatus.CREATED)
  async postByIdRefund(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: RefundPaymentRequest,
  ): Promise<Refund> {
    const payment = await this.paymentRepository.findOne({ id: id });
    if (!payment) {
      throw new NotFoundException("Not found");
    }
    if ((!payment.canRefund)) {
      throw new BadRequestException(`Cannot refund payment in status: ${payment.status}`);
    }
    // Calculate total already refunded to prevent over-refunding
    let totalRefunded: number = Number(0);
    for (const refund of payment.refunds) {
      if (refund.isSuccessful) {
        totalRefunded = (totalRefunded + refund.amount);
      }
    }
    if (((totalRefunded + body.amount) > payment.amount)) {
      throw new BadRequestException('Refund amount exceeds original payment');
    }
    const refund = this.refundRepository.create({ payment: payment, amount: body.amount, reason: body.reason, status: PaymentStatus.Pending } as never);
    await this.refundRepository.getEntityManager().persistAndFlush(refund);
    let success: boolean = await processRefundViaGateway(payment, refund);
    if (success) {
      refund.status = PaymentStatus.Completed;
      refund.processedAt = new Date();
      await this.refundRepository.getEntityManager().persistAndFlush(refund);
      let newTotalRefunded: number = (totalRefunded + body.amount);
      if ((newTotalRefunded >= payment.amount)) {
        payment.status = PaymentStatus.Refunded;
        await this.paymentRepository.getEntityManager().persistAndFlush(payment);
      }
    } else {
      refund.status = PaymentStatus.Failed;
      await this.refundRepository.getEntityManager().persistAndFlush(refund);
    }
    return refund;
  }

  @Get(':id')
  async getPayment(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<Payment> {
    return this.paymentService.findOne(id);
  }

}

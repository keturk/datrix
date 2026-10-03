import {
  Controller,
  Post,
  Param,
  Body,
  HttpCode,
  HttpStatus,
  UseGuards,
} from '@nestjs/common';
import { AuthGuard } from '../auth/auth.guard';
import { RateLimitGuard } from '../rate-limit/rate-limit.guard';
import { PrincipalTypes } from '../auth/optional-auth.decorator';
import { Providers } from '../auth/providers.decorator';
import { ApiKeyVerifyRequest } from '../dto/api-key-verify-request.struct';
import { ApiKeyVerifyResponse } from '../auth/api-key-verify';
import { answerApiKeyVerifyRequest } from '../auth/api-key-verify';
import { ApiExtraModels, ApiExcludeEndpoint, ApiBearerAuth } from '@nestjs/swagger';

@ApiExtraModels(ApiKeyVerifyRequest)
@UseGuards(AuthGuard, RateLimitGuard)
@Controller('internal/identity/api-keys')
export class _api_key_verifyController {
  constructor(
  ) {}

  @Providers('platform', 'test_auth')
  @PrincipalTypes('machine')
  @ApiExcludeEndpoint()
  @ApiBearerAuth()
  @Post('customerKeys/verify')
  @HttpCode(HttpStatus.CREATED)
  async postCustomerKeysVerify(
    @Body() body: ApiKeyVerifyRequest,
  ): Promise<ApiKeyVerifyResponse> {
    return answerApiKeyVerifyRequest("customerKeys", body.keyHash);
  }

}

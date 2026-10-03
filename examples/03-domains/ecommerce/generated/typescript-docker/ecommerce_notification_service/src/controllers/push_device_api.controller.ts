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
import { PrincipalTypes } from '../auth/optional-auth.decorator';
import { Providers } from '../auth/providers.decorator';
import { RegisterDeviceRequest } from '../dto/register-device-request.struct';
import { ApiExtraModels, ApiBearerAuth } from '@nestjs/swagger';

@ApiExtraModels(RegisterDeviceRequest)
@UseGuards(AuthGuard)
@Controller('push')
export class PushDeviceApiController {
  constructor(
  ) {}

  @Providers('identity', 'test_auth')
  @PrincipalTypes('human')
  @ApiBearerAuth()
  @Post('devices')
  @HttpCode(HttpStatus.CREATED)
  async postDevices(
    @Body() body: RegisterDeviceRequest,
  ): Promise<void> {
    
  }

  @Providers('identity', 'test_auth')
  @PrincipalTypes('human')
  @ApiBearerAuth()
  @Post('devices/unregister')
  @HttpCode(HttpStatus.CREATED)
  async postDevicesUnregister(
    @Body() body: RegisterDeviceRequest,
  ): Promise<void> {
    
  }

}

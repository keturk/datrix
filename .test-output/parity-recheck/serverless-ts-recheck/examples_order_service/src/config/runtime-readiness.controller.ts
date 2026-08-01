/**
 * Internal readiness route. Auto-generated. Do not edit.
 *
 * Exposes GET /internal/readiness. Resolves every required config key and
 * secret handle through the SAME RemoteConfigClient/SecretsService instances
 * the rest of the app uses, then returns the value-free readiness report:
 * HTTP 200 when every required item resolves, HTTP 503 otherwise. The JSON
 * body carries identities and statuses only -- never a resolved value.
 */
import { Controller, Get, HttpStatus, Res } from '@nestjs/common';
import { ApiExcludeEndpoint } from '@nestjs/swagger';
import type { Response } from 'express';
import { RemoteConfigClient } from './remoteConfig';
import { SecretsService } from '../examples_order_service/secrets/secrets.service';
import { checkRuntimeReadiness } from './runtimeReadiness';

@Controller()
export class RuntimeReadinessController {
  constructor(
    private readonly configClient: RemoteConfigClient,
    private readonly secrets: SecretsService,
  ) {}

  @Get('/internal/readiness')
  @ApiExcludeEndpoint()
  async readiness(@Res() res: Response): Promise<void> {
    const { configClient, secrets } = this;
    const report = await checkRuntimeReadiness(configClient, secrets);
    const body = {
      ok: report.ok,
      items: report.items.map((item) => ({
        kind: item.kind,
        name: item.logicalName,
        rendered: item.renderedName,
        status: item.status,
        detail: item.detail,
      })),
    };
    const status = report.ok ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE;
    res.status(status).json(body);
  }
}

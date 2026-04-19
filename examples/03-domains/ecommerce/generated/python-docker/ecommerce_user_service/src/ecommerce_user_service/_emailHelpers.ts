/**
 * Email helper functions for generated TypeScript code.
 *
 * Provider: sendgrid
 *
 * Exports _emailSend, _emailSendTemplate, and _emailSendBulk with unified
 * signatures regardless of the configured email provider.
 */
import * as sgMail from '@sendgrid/mail';

interface EmailOptions {
  from?: string;
}

export interface EmailPayload {
  to: string;
  subject?: string;
  body?: string;
  template?: string;
  data?: Record<string, unknown>;
  from?: string;
}

function _getSendGrid(): typeof sgMail {
  const apiKey = process.env.SENDGRID_API_KEY;
  if (!apiKey) {
    throw new Error('SENDGRID_API_KEY environment variable is required');
  }
  sgMail.setApiKey(apiKey);
  return sgMail;
}

function _resolveSender(options?: EmailOptions): string {
  const from = options?.from ?? process.env.SENDGRID_FROM_EMAIL;
  if (!from) {
    throw new Error(
      'Email sender not configured. Provide options.from or set SENDGRID_FROM_EMAIL.',
    );
  }
  return from;
}

export async function _emailSend(payload: EmailPayload): Promise<void> {
  const { to, subject = '', body = '', template, data, from } = payload;
  const options: EmailOptions | undefined = from !== undefined ? { from } : undefined;
  const sg = _getSendGrid();

  if (template) {
    await sg.send({
      to,
      from: _resolveSender(options),
      templateId: template,
      dynamicTemplateData: data ?? {},
    });
  } else {
    await sg.send({
      to,
      from: _resolveSender(options),
      subject,
      text: body,
    });
  }
}

export async function _emailSendTemplate(payload: EmailPayload): Promise<void> {
  const { to, template = '', data = {}, from } = payload;
  const options: EmailOptions | undefined = from !== undefined ? { from } : undefined;
  const sg = _getSendGrid();

  await sg.send({
    to,
    from: _resolveSender(options),
    templateId: template,
    dynamicTemplateData: data,
  });
}

export async function _emailSendBulk(
  recipients: string[],
  subject: string,
  body: string,
  options?: EmailOptions,
): Promise<void> {
  const sg = _getSendGrid();
  const from = _resolveSender(options);

  await Promise.all(
    recipients.map((to) =>
      sg.send({
        to,
        from,
        subject,
        text: body,
      }),
    ),
  );
}

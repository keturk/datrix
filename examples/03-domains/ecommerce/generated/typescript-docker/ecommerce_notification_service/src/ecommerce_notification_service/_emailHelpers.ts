/**
 * Email helper functions for generated TypeScript code.
 *
 * Provider: smtp
 *
 * Exports _emailSend, _emailSendTemplate, and _emailSendBulk with unified
 * signatures regardless of the configured email provider.
 */
import nodemailer from 'nodemailer';

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

function _getTransport(): nodemailer.Transporter {
  return nodemailer.createTransport({
    host: (() => { if (!process.env.SMTP_HOST) throw new Error('SMTP_HOST environment variable is required'); return process.env.SMTP_HOST; })(),
    port: parseInt((() => { if (!process.env.SMTP_PORT) throw new Error('SMTP_PORT environment variable is required'); return process.env.SMTP_PORT; })(), 10),
    secure: process.env.SMTP_SECURE === 'true',
    auth:
      process.env.SMTP_USER
        ? { user: process.env.SMTP_USER, pass: (() => { if (!process.env.SMTP_PASS) throw new Error('SMTP_PASS environment variable is required'); return process.env.SMTP_PASS; })() }
        : undefined,
  });
}

function _resolveSender(options?: EmailOptions): string {
  const from = options?.from ?? process.env.SMTP_FROM;
  if (!from) {
    throw new Error(
      'Email sender not configured. Provide options.from or set SMTP_FROM.',
    );
  }
  return from;
}

export async function _emailSend(payload: EmailPayload): Promise<void> {
  const { to, subject = '', body = '', template, data, from } = payload;
  const options: EmailOptions | undefined = from !== undefined ? { from } : undefined;
  if (template) {
    const text = JSON.stringify(data ?? {});
    await _getTransport().sendMail({
      from: _resolveSender(options),
      to,
      subject: template,
      text,
    });
  } else {
    await _getTransport().sendMail({
      from: _resolveSender(options),
      to,
      subject,
      text: body,
    });
  }
}

export async function _emailSendTemplate(payload: EmailPayload): Promise<void> {
  const { to, template = '', data = {}, from } = payload;
  const options: EmailOptions | undefined = from !== undefined ? { from } : undefined;
  const body = JSON.stringify(data ?? {});
  await _getTransport().sendMail({
    from: _resolveSender(options),
    to,
    subject: template,
    text: body,
  });
}

export async function _emailSendBulk(
  recipients: string[],
  subject: string,
  body: string,
  options?: EmailOptions,
): Promise<void> {
  const transport = _getTransport();
  const from = _resolveSender(options);
  await Promise.all(
    recipients.map((to) =>
      transport.sendMail({ from, to, subject, text: body }),
    ),
  );
}

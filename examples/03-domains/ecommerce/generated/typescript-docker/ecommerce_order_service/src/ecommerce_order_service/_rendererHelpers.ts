/**
 * Renderer helpers for Datrix ``Renderer.toPdf`` and ``Renderer.toPng`` builtins.
 * Renders HTML templates to PDF or PNG via Puppeteer.
 */

import puppeteer from 'puppeteer';
import type { PaperFormat } from 'puppeteer';

function _buildHtml(template: string, data: unknown): string {
  return `<html><body><h1>${template}</h1><pre>${JSON.stringify(data, null, 2)}</pre></body></html>`;
}

export async function _rendererToPdf(
  options: Record<string, unknown>,
): Promise<Buffer> {
  const template = String(options.template ?? '');
  const data = options.data ?? {};
  const pageSize = String(options.pageSize ?? 'A4');
  const landscape = Boolean(options.landscape ?? false);

  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  const html = _buildHtml(template, data);
  await page.setContent(html, { waitUntil: 'load' });
  const pdf = await page.pdf({
    format: pageSize as PaperFormat,
    landscape,
    printBackground: true,
  });
  await browser.close();
  return Buffer.from(pdf);
}

export async function _rendererToPng(
  options: Record<string, unknown>,
): Promise<Buffer> {
  const template = String(options.template ?? '');
  const data = options.data ?? {};
  const width = Number(options.width ?? 1920);
  const height = Number(options.height ?? 1080);

  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width, height });
  const html = _buildHtml(template, data);
  await page.setContent(html, { waitUntil: 'load' });
  const png = await page.screenshot({ fullPage: true, type: 'png' });
  await browser.close();
  return Buffer.from(png);
}

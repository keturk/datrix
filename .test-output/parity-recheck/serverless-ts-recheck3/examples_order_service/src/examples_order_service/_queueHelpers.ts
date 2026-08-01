/**
 * Queue helper functions for generated TypeScript code.
 *
 * Uses amqplib for AMQP operations. Each helper manages its own connection
 * lifecycle for simplicity.
 */
import * as amqp from 'amqplib';

const _DEFAULT_JOB_QUEUE_NAME = 'datrix.jobs.examples_order_service';

function _amqpUrl(): string {
  if (!process.env.AMQP_URL) throw new Error('AMQP_URL environment variable is required');
  return process.env.AMQP_URL;
}

export async function _queuePublish(
  queue: string,
  message: unknown,
): Promise<void> {
  const conn = await amqp.connect(_amqpUrl());
  const ch = await conn.createChannel();
  await ch.assertQueue(queue);
  ch.sendToQueue(queue, Buffer.from(JSON.stringify(message)));
  await ch.close();
  await conn.close();
}

export async function _queueSubscribe(
  queue: string,
  handler: (msg: unknown, channel: amqp.Channel) => void,
): Promise<void> {
  const conn = await amqp.connect(_amqpUrl());
  const ch = await conn.createChannel();
  await ch.assertQueue(queue);
  ch.consume(queue, (msg: amqp.ConsumeMessage | null) => {
    if (msg) handler(JSON.parse(msg.content.toString()), ch);
  });
}

export async function _queuePurge(queue: string): Promise<number> {
  const conn = await amqp.connect(_amqpUrl());
  const ch = await conn.createChannel();
  const result = await ch.purgeQueue(queue);
  await ch.close();
  await conn.close();
  return result.messageCount;
}

export async function _queueLength(queue: string): Promise<number> {
  const conn = await amqp.connect(_amqpUrl());
  const ch = await conn.createChannel();
  const result = await ch.checkQueue(queue);
  await ch.close();
  await conn.close();
  return result.messageCount;
}

export async function _queueDelay(
  queue: string,
  message: unknown,
  delayMs: number,
): Promise<void> {
  const conn = await amqp.connect(_amqpUrl());
  const ch = await conn.createChannel();
  await ch.assertQueue(queue);
  ch.sendToQueue(queue, Buffer.from(JSON.stringify(message)), {
    expiration: String(delayMs * 1000),
  });
  await ch.close();
  await conn.close();
}

export async function _queueEnqueueJob(
  jobType: string,
  jobPayload: unknown,
): Promise<void> {
  const queueName = process.env.DIX_JOB_QUEUE_NAME ?? _DEFAULT_JOB_QUEUE_NAME;
  const body = { job: jobType, payload: jobPayload };
  const conn = await amqp.connect(_amqpUrl());
  const ch = await conn.createChannel();
  await ch.assertQueue(queueName, { durable: true });
  ch.sendToQueue(queueName, Buffer.from(JSON.stringify(body)), { persistent: true });
  await ch.close();
  await conn.close();
}

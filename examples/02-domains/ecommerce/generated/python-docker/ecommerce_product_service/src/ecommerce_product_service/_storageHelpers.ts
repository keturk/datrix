/**
 * Storage helper functions for generated TypeScript code.
 *
 * Uses AWS S3 (SDK v3) for object storage operations. The S3 client is
 * initialized from AWS_REGION and AWS_S3_BUCKET environment variables.
 */
import {
  S3Client,
  PutObjectCommand,
  GetObjectCommand,
  DeleteObjectCommand,
  HeadObjectCommand,
  ListObjectsV2Command,
  CopyObjectCommand,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { Readable } from 'stream';

function _getS3(): S3Client {
  if (!process.env.AWS_REGION) throw new Error('AWS_REGION environment variable is required');
  return new S3Client({ region: process.env.AWS_REGION });
}

function _getBucket(): string {
  const bucket = process.env.AWS_S3_BUCKET;
  if (!bucket) {
    throw new Error('AWS_S3_BUCKET environment variable is not set.');
  }
  return bucket;
}

export async function _storageUpload(
  path: string,
  content: Buffer | string | Readable,
  options?: Record<string, unknown>,
): Promise<void> {
  await _getS3().send(
    new PutObjectCommand({
      Bucket: _getBucket(),
      Key: path,
      Body: content,
      ContentType: (options?.contentType as string) ?? 'application/octet-stream',
    }),
  );
}

export async function _storageDownload(path: string): Promise<Buffer> {
  const result = await _getS3().send(
    new GetObjectCommand({ Bucket: _getBucket(), Key: path }),
  );
  const chunks: Uint8Array[] = [];
  for await (const chunk of result.Body as Readable) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

export async function _storageDelete(path: string): Promise<void> {
  await _getS3().send(
    new DeleteObjectCommand({ Bucket: _getBucket(), Key: path }),
  );
}

export async function _storageExists(path: string): Promise<boolean> {
  try {
    await _getS3().send(
      new HeadObjectCommand({ Bucket: _getBucket(), Key: path }),
    );
    return true;
  } catch (err: unknown) {
    const name = (err as { name?: string }).name;
    if (name === 'NotFound' || name === 'NoSuchKey') return false;
    throw err;
  }
}

export async function _storageList(prefix: string): Promise<string[]> {
  const result = await _getS3().send(
    new ListObjectsV2Command({ Bucket: _getBucket(), Prefix: prefix }),
  );
  return (result.Contents ?? []).map((obj) => obj.Key ?? '');
}

export async function _storageGetUrl(
  path: string,
  expiresIn?: number,
): Promise<string> {
  const cmd = new GetObjectCommand({ Bucket: _getBucket(), Key: path });
  return getSignedUrl(_getS3(), cmd, { expiresIn: expiresIn ?? 3600 });
}

export async function _storageCopy(source: string, dest: string): Promise<void> {
  await _getS3().send(
    new CopyObjectCommand({
      Bucket: _getBucket(),
      CopySource: `${_getBucket()}/${source}`,
      Key: dest,
    }),
  );
}

export async function _storageMove(source: string, dest: string): Promise<void> {
  await _storageCopy(source, dest);
  await _storageDelete(source);
}

export async function _storageGetMetadata(
  path: string,
): Promise<Record<string, string>> {
  const result = await _getS3().send(
    new HeadObjectCommand({ Bucket: _getBucket(), Key: path }),
  );
  return result.Metadata ?? {};
}

export async function _storageSetMetadata(
  path: string,
  metadata: Record<string, string>,
): Promise<void> {
  await _getS3().send(
    new CopyObjectCommand({
      Bucket: _getBucket(),
      CopySource: `${_getBucket()}/${path}`,
      Key: path,
      Metadata: metadata,
      MetadataDirective: 'REPLACE',
    }),
  );
}

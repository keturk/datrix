/**
 * Storage helper functions for generated TypeScript code.
 *
 * Dispatches on the storage block's provider (minio). Bucket and
 * region are baked at generation time from the storage block declaration;
 * no ambient AWS_REGION / AWS_S3_BUCKET environment variables are read.
 * MinIO and Azure Blob still resolve their own runtime credentials from
 * their provider-specific environment variables.
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

const _BUCKET: string = 'product-images';

function _getBucket(): string {
  if (!_BUCKET) throw new Error('Storage bucket was not configured on the storage block at generation time.');
  return _BUCKET;
}

function _getS3(): S3Client {
  const endpoint = 'http://localhost:9000';
  if (!endpoint) {
    throw new Error('MinIO storage requires an "endpoint" configured on the storage block.');
  }
  const accessKeyId = process.env.MINIO_ACCESS_KEY;
  const secretAccessKey = process.env.MINIO_SECRET_KEY;
  if (!accessKeyId || !secretAccessKey) {
    throw new Error('MINIO_ACCESS_KEY and MINIO_SECRET_KEY environment variables are required');
  }
  return new S3Client({
    endpoint,
    region: 'us-east-1',
    credentials: { accessKeyId, secretAccessKey },
    forcePathStyle: true,
  });
}

export async function _storageUpload(
  path: string,
  content: Buffer | string | Readable,
  options?: Record<string, unknown>,
): Promise<void> {
  const contentType = (options?.contentType as string) ?? 'application/octet-stream';
  await _getS3().send(
    new PutObjectCommand({
      Bucket: _getBucket(),
      Key: path,
      Body: content,
      ContentType: contentType,
    }),
  );
}

export async function _storageBlockUpload(
  pathOrContent: string | Buffer | Readable,
  contentOrOptions?: string | Buffer | Readable | Record<string, unknown>,
  maybeOptions?: Record<string, unknown>,
): Promise<string> {
  if (typeof pathOrContent === 'string' && contentOrOptions !== undefined && !(contentOrOptions instanceof Readable) && (typeof contentOrOptions === 'string' || Buffer.isBuffer(contentOrOptions))) {
    await _storageUpload(pathOrContent, contentOrOptions, maybeOptions);
    return pathOrContent;
  }
  const options = (contentOrOptions ?? {}) as Record<string, unknown>;
  const folder = (options.folder as string) ?? '';
  const filename = (options.filename as string) ?? 'upload';
  const path = folder ? `${folder}/${filename}` : filename;
  await _storageUpload(path, pathOrContent, options);
  return path;
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

export async function _storagePresignedUrl(
  blockOrPath: string,
  pathOrExpiresIn?: string | number,
  maybeExpiresIn?: number,
): Promise<string> {
  const path = typeof pathOrExpiresIn === 'string' ? pathOrExpiresIn : blockOrPath;
  const expiresIn = typeof pathOrExpiresIn === 'number' ? pathOrExpiresIn : maybeExpiresIn;
  return _storageGetUrl(path, expiresIn);
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

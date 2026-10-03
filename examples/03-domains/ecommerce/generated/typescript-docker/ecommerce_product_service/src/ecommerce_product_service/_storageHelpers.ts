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

/**
 * Longest lifetime a signed download link may carry: seven days. S3 SigV4
 * presigning, GCS V4 signed URLs and Azure SAS tokens all stop at this bound,
 * and the storage rejects a longer link only when it is opened.
 */
export const PRESIGNED_URL_MAX_EXPIRES_SECONDS = 604800;

function _validateExpiresIn(expiresIn: number): void {
  if (Number.isInteger(expiresIn) && expiresIn > 0 && expiresIn <= PRESIGNED_URL_MAX_EXPIRES_SECONDS) {
    return;
  }
  throw new Error(
    `expiresIn=${expiresIn} is outside the presigned URL lifetime range: expected an integer ` +
      `between 1 and ${PRESIGNED_URL_MAX_EXPIRES_SECONDS} seconds (seven days). Pass a shorter expiry to getUrl().`,
  );
}

function _minioClient(endpoint: string): S3Client {
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

function _getS3(): S3Client {
  return _minioClient('http://localhost:3900');
}

/**
 * The client that signs download links: bound to the public endpoint -- the
 * address a browser reaches MinIO on, which differs from the API endpoint
 * whenever this service reaches MinIO over a private network. S3 signatures
 * cover the host, so the link is signed for the public host up front, never
 * rewritten afterwards.
 */
function _getPresigner(): S3Client {
  return _minioClient('http://localhost:3900');
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
  const lifetime = expiresIn ?? 3600;
  _validateExpiresIn(lifetime);
  const cmd = new GetObjectCommand({ Bucket: _getBucket(), Key: path });
  return getSignedUrl(_getPresigner(), cmd, { expiresIn: lifetime });
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

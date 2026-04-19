import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import axios, { AxiosInstance, AxiosError } from 'axios';

@Injectable()
export class UserServiceHttpClient {
  private readonly logger = new Logger(UserServiceHttpClient.name);
  private readonly httpClient: AxiosInstance;

  constructor(private readonly configService: ConfigService) {
    const baseUrl = this.configService.getOrThrow<string>('USER_SERVICE_BASE_URL');
    this.httpClient = axios.create({
      baseURL: baseUrl,
      timeout: 10000,
      headers: { 'Content-Type': 'application/json' },
    });
    this.httpClient.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        this.logger.error(`Request failed: ${error.message}`, {
          url: error.config?.url,
          status: error.response?.status,
        });
        throw error;
      },
    );
  }

  async get<T>(path: string): Promise<T> {
    const { data } = await this.httpClient.get<T>(path);
    return data;
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const { data } = await this.httpClient.post<T>(path, body);
    return data;
  }
}

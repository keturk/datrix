package library_book_service.cache.redis;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Cache connection settings, resolved at build time from the declared cache block config (no
 * environment variables are read at runtime).
 *
 * <p>The Redis/Valkey connection string defaults to {@code redis://localhost:6379}.
 */
@Component("redisCacheProperties")
@ConfigurationProperties(prefix = "datrix.cache.redis")
public class CacheProperties {

  private String url = "redis://localhost:6379";
  private int poolSize = 10;

  public String url() {
    return url;
  }

  public void setUrl(String url) {
    this.url = url;
  }

  public int poolSize() {
    return poolSize;
  }

  public void setPoolSize(int poolSize) {
    this.poolSize = poolSize;
  }
}

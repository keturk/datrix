package ecommerce_user_service.cache.redis;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component("redisCacheDecorators")
public class CacheDecorators {

  private static final Logger log = LoggerFactory.getLogger(CacheDecorators.class);
  private static final int KEY_MAX_LENGTH = 100;
  private static final int DEFAULT_TTL_SECONDS = 300;

  private final StringRedisTemplate redis;
  private final ObjectMapper objectMapper;

  public CacheDecorators(
      StringRedisTemplate redisCacheStringRedisTemplate, ObjectMapper objectMapper) {
    this.redis = redisCacheStringRedisTemplate;
    this.objectMapper = objectMapper;
  }

  /**
   * Build a well-formed cache key from a prefix and argument list, hashed down to a fixed-length
   * digest when the literal concatenation would exceed {@link #KEY_MAX_LENGTH}.
   */
  public static String makeCacheKey(String prefix, Object... args) {
    StringBuilder sb = new StringBuilder(prefix);
    for (Object arg : args) {
      sb.append(':').append(arg);
    }
    String key = sb.toString();
    if (key.length() > KEY_MAX_LENGTH) {
      return prefix + ":" + Integer.toHexString(key.hashCode());
    }
    return key;
  }

  /**
   * Read-through cache: return the cached value at {@code key} if present, else invoke {@code
   * supplier}, cache its (non-null) result for {@code ttlSeconds} (or {@link #DEFAULT_TTL_SECONDS}
   * when {@code ttlSeconds <= 0}), and return it.
   */
  public <T> T cached(String key, int ttlSeconds, Class<T> type, Supplier<T> supplier) {
    T fromCache = readCached(key, type);
    if (fromCache != null) {
      return fromCache;
    }
    T result = supplier.get();
    if (result != null) {
      writeCached(key, ttlSeconds, result);
    }
    return result;
  }

  /**
   * Read-through cache for a {@code List<T>}-returning endpoint handler. Java erases generic type
   * arguments at runtime, so a {@code List<T>} response cannot deserialize through the plain {@code
   * Class<T>} overload above ({@code List.class} alone carries no element-type information) -- this
   * overload takes the element {@link Class} and reconstructs the full collection {@link JavaType}
   * via the {@link ObjectMapper}'s {@code TypeFactory} instead.
   */
  public <T> List<T> cachedList(
      String key, int ttlSeconds, Class<T> elementType, Supplier<List<T>> supplier) {
    List<T> fromCache = readCachedList(key, elementType);
    if (fromCache != null) {
      return fromCache;
    }
    List<T> result = supplier.get();
    if (result != null) {
      writeCached(key, ttlSeconds, result);
    }
    return result;
  }

  private <T> T readCached(String key, Class<T> type) {
    String raw = readRaw(key);
    if (raw == null) {
      return null;
    }
    try {
      return objectMapper.readValue(raw, type);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("Failed to deserialize cached value for key " + key, e);
    }
  }

  private <T> List<T> readCachedList(String key, Class<T> elementType) {
    String raw = readRaw(key);
    if (raw == null) {
      return null;
    }
    JavaType listType =
        objectMapper.getTypeFactory().constructCollectionType(List.class, elementType);
    try {
      return objectMapper.readValue(raw, listType);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("Failed to deserialize cached value for key " + key, e);
    }
  }

  private String readRaw(String key) {
    try {
      return redis.opsForValue().get(key);
    } catch (DataAccessException e) {
      throw new IllegalStateException("Cache read failed for key " + key, e);
    }
  }

  private <T> void writeCached(String key, int ttlSeconds, T value) {
    String json;
    try {
      json = objectMapper.writeValueAsString(value);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("Failed to serialize value for key " + key, e);
    }
    int effectiveTtl = ttlSeconds > 0 ? ttlSeconds : DEFAULT_TTL_SECONDS;
    try {
      redis.opsForValue().set(key, json, java.time.Duration.ofSeconds(effectiveTtl));
    } catch (DataAccessException e) {
      throw new IllegalStateException("Cache write failed for key " + key, e);
    }
  }

  /** Invalidate {@code key} (e.g. after a mutating operation completes). */
  public void invalidate(String key) {
    try {
      redis.delete(key);
    } catch (DataAccessException e) {
      // Degraded per dependencyPolicy: surfaced at WARN (never silent) --
      // `key` may now serve stale data until its TTL expires.
      log.warn(
          "cache_invalidation_failed key={} (degraded per dependencyPolicy: "
              + "key may serve stale data until TTL expiry)",
          key,
          e);
    }
  }
}

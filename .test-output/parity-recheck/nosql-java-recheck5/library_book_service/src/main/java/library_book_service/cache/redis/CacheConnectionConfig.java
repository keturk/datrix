package library_book_service.cache.redis;

import java.net.URI;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class CacheConnectionConfig {

  /**
   * Redis/Valkey connection factory. URL is sourced from {@link CacheProperties} (assembled at
   * build time from the resolved cache block config -- zero environment variables are read at
   * runtime).
   */
  @Bean
  public LettuceConnectionFactory redisCacheRedisConnectionFactory(CacheProperties properties) {
    URI redisUri = URI.create(properties.url());
    RedisStandaloneConfiguration serverConfig =
        new RedisStandaloneConfiguration(
            redisUri.getHost(), redisUri.getPort() > 0 ? redisUri.getPort() : 6379);
    LettuceClientConfiguration clientConfig = LettuceClientConfiguration.builder().build();
    return new LettuceConnectionFactory(serverConfig, clientConfig);
  }

  @Bean
  public StringRedisTemplate redisCacheStringRedisTemplate(
      LettuceConnectionFactory redisCacheRedisConnectionFactory) {
    return new StringRedisTemplate(redisCacheRedisConnectionFactory);
  }
}

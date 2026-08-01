package library_book_service.config;

import java.util.ArrayList;
import java.util.List;

/**
 * Strict runtime readiness check. Auto-generated. Do not edit.
 *
 * <p>Resolves every required config key and secret handle through the SAME runtime clients the
 * application uses ({@code RemoteConfig} from {@code library_book_service}) once that client is
 * wired. Reports status by logical handle/key and rendered platform name. NEVER captures, logs, or
 * returns a resolved value.
 */
public final class RuntimeReadiness {

  private RuntimeReadiness() {}

  public enum ReadinessStatus {
    OK,
    MISSING,
    ERROR
  }

  public record ReadinessItem(
      String kind,
      String logicalName,
      String renderedName,
      ReadinessStatus status,
      String detail) {}

  public record ReadinessReport(boolean ok, List<ReadinessItem> items) {}

  @FunctionalInterface
  public interface SecretResolver {
    String resolve(String logicalName) throws Exception;
  }

  @FunctionalInterface
  public interface ConfigResolver {
    String resolve(String logicalName) throws Exception;
  }

  // Required set baked from the runtime-requirements manifest. Each entry:
  // {logical_name, rendered_name}. Values are NEVER baked here.
  public static final List<String[]> REQUIRED_SECRET_HANDLES =
      List.<String[]>of(
          new String[] {"book_db_password", "book_db_password"},
          new String[] {"docdb_secret-key", "docdb_secret-key"},
          new String[] {"trusted_caller_secret", "trusted_caller_secret"});

  public static final List<String[]> REQUIRED_CONFIG_KEYS =
      List.<String[]>of(
          new String[] {"book_db_database", "book_db_database"},
          new String[] {"book_db_host", "book_db_host"},
          new String[] {"book_db_port", "book_db_port"},
          new String[] {"book_db_user", "book_db_user"},
          new String[] {"docdb_database", "docdb_database"},
          new String[] {"docdb_host", "docdb_host"},
          new String[] {"docdb_port", "docdb_port"},
          new String[] {"docdb_user", "docdb_user"},
          new String[] {"mq_brokers", "mq_brokers"},
          new String[] {"mq_port", "mq_port"},
          new String[] {"redis_database", "redis_database"},
          new String[] {"redis_host", "redis_host"},
          new String[] {"redis_port", "redis_port"});

  /**
   * Resolve every required item through the caller-supplied resolvers. Returns a value-free report
   * -- no resolved value is ever bound outside the resolution call itself.
   */
  public static ReadinessReport check(SecretResolver secrets, ConfigResolver config) {
    List<ReadinessItem> items = new ArrayList<>();
    for (String[] pair : REQUIRED_SECRET_HANDLES) {
      items.add(probe("secret", pair[0], pair[1], () -> secrets.resolve(pair[0])));
    }
    for (String[] pair : REQUIRED_CONFIG_KEYS) {
      items.add(probe("config", pair[0], pair[1], () -> config.resolve(pair[0])));
    }
    boolean ok = items.stream().noneMatch(item -> item.status() != ReadinessStatus.OK);
    return new ReadinessReport(ok, items);
  }

  @FunctionalInterface
  private interface Resolve {
    String get() throws Exception;
  }

  private static ReadinessItem probe(
      String kind, String logical, String rendered, Resolve resolve) {
    try {
      resolve.get();
      return new ReadinessItem(kind, logical, rendered, ReadinessStatus.OK, "resolved");
    } catch (Exception e) {
      return new ReadinessItem(
          kind,
          logical,
          rendered,
          ReadinessStatus.ERROR,
          e.getClass().getSimpleName() + ": " + e.getMessage());
    }
  }
}

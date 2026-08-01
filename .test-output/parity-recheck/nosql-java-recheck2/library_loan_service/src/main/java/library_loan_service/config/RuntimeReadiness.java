package library_loan_service.config;

import java.util.ArrayList;
import java.util.List;

/**
 * Strict runtime readiness check. Auto-generated. Do not edit.
 *
 * <p>Resolves every required config key and secret handle through the SAME runtime clients the
 * application uses ({@code RemoteConfig} from {@code library_loan_service}) once that client is
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
      List.<String[]>of(new String[] {"loan_db_password", "loan_db_password"});

  public static final List<String[]> REQUIRED_CONFIG_KEYS =
      List.<String[]>of(
          new String[] {"library_book_service_base_url", "library_book_service_base_url"},
          new String[] {"library_member_service_base_url", "library_member_service_base_url"},
          new String[] {"loan_db_database", "loan_db_database"},
          new String[] {"loan_db_host", "loan_db_host"},
          new String[] {"loan_db_port", "loan_db_port"},
          new String[] {"loan_db_user", "loan_db_user"});

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

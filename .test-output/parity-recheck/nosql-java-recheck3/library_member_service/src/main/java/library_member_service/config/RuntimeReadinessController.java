package library_member_service.config;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Internal readiness route. Auto-generated. Do not edit.
 *
 * <p>Exposes {@code GET /internal/readiness}. Uses whichever {@link
 * RuntimeReadiness.SecretResolver} / {@link RuntimeReadiness.ConfigResolver} beans are registered;
 * returns the value-free readiness report: HTTP 200 when every required item resolves, HTTP 503
 * otherwise. The JSON body carries identities and statuses only -- never a resolved value.
 */
@RestController
public class RuntimeReadinessController {

  private static final int HTTP_SERVICE_UNAVAILABLE = 503;

  private final Optional<RuntimeReadiness.SecretResolver> secretResolver;
  private final Optional<RuntimeReadiness.ConfigResolver> configResolver;

  public RuntimeReadinessController(
      Optional<RuntimeReadiness.SecretResolver> secretResolver,
      Optional<RuntimeReadiness.ConfigResolver> configResolver) {
    this.secretResolver = secretResolver;
    this.configResolver = configResolver;
  }

  @GetMapping("/internal/readiness")
  public ResponseEntity<Map<String, Object>> readiness() {
    if (secretResolver.isEmpty() || configResolver.isEmpty()) {
      Map<String, Object> body = new LinkedHashMap<>();
      body.put("ok", false);
      body.put(
          "detail", "No SecretResolver/ConfigResolver bean is registered yet for this deployment.");
      return ResponseEntity.status(HTTP_SERVICE_UNAVAILABLE).body(body);
    }
    RuntimeReadiness.ReadinessReport report =
        RuntimeReadiness.check(secretResolver.get(), configResolver.get());
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("ok", report.ok());
    body.put("items", report.items());
    return report.ok()
        ? ResponseEntity.ok(body)
        : ResponseEntity.status(HTTP_SERVICE_UNAVAILABLE).body(body);
  }
}

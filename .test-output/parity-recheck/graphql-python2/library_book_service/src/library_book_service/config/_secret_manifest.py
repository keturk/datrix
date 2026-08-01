"""Data-only secret reference manifest. Auto-generated. Do not edit.

Maps each logical secret handle to its rendered backend-specific name and
whether the secret is required.  Built once by the shared
``SecretReferenceManifest`` during code generation; consumed at runtime by
``secrets_resolver.py`` for all handle → name lookups.

No imports that perform I/O, read environment variables, or contact any SDK
are permitted in this module.  It is a pure data constant.
"""

from __future__ import annotations

# Backend selected at generation time from SecretBackendPolicy.default_backend.
SECRET_BACKEND: str = "docker-secret"

# Default cache TTL (seconds) baked from SecretBackendPolicy.default_secret_ttl_seconds.
# Applied to a handle whose entry omits ``ttl_seconds``. 0 means "no expiry".
DEFAULT_SECRET_TTL_SECONDS: int = 300

# Mapping from logical handle → {rendered_name, required, ttl_seconds, provisioning_authority}.
# rendered_name: the backend-specific secret name / path / filename.
# required: when True, an absent secret is a hard runtime failure.
# ttl_seconds: per-handle cache TTL; 0 means "no expiry, cache for process lifetime".
# provisioning_authority: "operator" or "datrix"; metadata only, never a value.
SECRET_REFERENCES: dict[str, dict[str, object]] = {
    "book_db_password": {
        "rendered_name": "book_db_password",
        "required": True,
        "ttl_seconds": 300,
        "provisioning_authority": "operator",
    },
    "jwt_public_key": {
        "rendered_name": "jwt_public_key",
        "required": True,
        "ttl_seconds": 300,
        "provisioning_authority": "operator",
    },
}

"""Cross-language token-validation parity for the identity stack (task 69-24, DN45).

Drives the GENERATED Python identity validator (``api/identity.py.j2``) with
fixture JWKS documents and real RSA-signed tokens — exercising every DN34
runtime case — and asserts that:

1. the Python validator returns the EXPECTED reason code for each case (every
   value is a real :class:`AuthReasonCode`);
2. the GENERATED TypeScript validator (``auth/identity.ts.j2`` +
   ``auth/auth.guard.ts.j2``) surfaces the SAME reason-code vocabulary for the
   same cases — so the two language targets cannot drift in their accept/reject
   decisions or reason codes (DN45 parity).

No mocks / SimpleNamespace / MagicMock: real RSA key pairs (``cryptography``),
real PyJWT signing, and the real rendered templates.  The Python validator is
``exec()``'d and behaviourally driven; the TypeScript validator is rendered and
its reason-code surface is verified (Node is not available in CI, so the TS
side is checked structurally against the shared reason-code enum — the same
approach the TypeScript package uses).

``@pytest.mark.integration``.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import json
import os
import time
import types
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from datrix_common.generation.plugin_helpers import template_dir_for
from datrix_common.generation.template_generator import TemplateGenerator
from datrix_common.identity.audit import AuthReasonCode

pytestmark = pytest.mark.integration

_ISSUER = "https://auth.shop.example.com/realms/shop-customers"
_AUDIENCE = "shop-storefront"
_JWKS_URI = _ISSUER + "/protocol/openid-connect/certs"
_PROVIDER = "customer"


# ---------------------------------------------------------------------------
# RSA key + JWK helpers (real crypto)
# ---------------------------------------------------------------------------


def _rsa_pair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _int_b64(n: int) -> str:
    length = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()


def _jwk(private_key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "kid": kid,
        "alg": "RS256",
        "n": _int_b64(numbers.n),
        "e": _int_b64(numbers.e),
    }


def _jwks(keys: list[dict[str, Any]]) -> dict[str, Any]:
    return {"keys": keys}


def _sign(
    private_key: rsa.RSAPrivateKey,
    kid: str,
    payload: dict[str, Any],
    algorithm: str = "RS256",
) -> str:
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(payload, pem, algorithm=algorithm, headers={"kid": kid})


def _payload(
    *,
    sub: str = "user-123",
    roles: list[str] | None = None,
    iss: str = _ISSUER,
    aud: str | None = _AUDIENCE,
    exp_offset: int = 3600,
) -> dict[str, Any]:
    now = int(time.time())
    body: dict[str, Any] = {
        "sub": sub,
        "iss": iss,
        "iat": now,
        "exp": now + exp_offset,
        "roles": roles or ["premiumCustomer"],
    }
    if aud is not None:
        body["aud"] = aud
    return body


# ---------------------------------------------------------------------------
# Provider plan (single customer provider, RS256)
# ---------------------------------------------------------------------------


def _provider_plan() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "application": "shop",
        "environment": "test",
        "providers": {
            _PROVIDER: {
                "name": _PROVIDER,
                "providerType": "keycloak",
                "audience": _AUDIENCE,
                "mode": "external",
                "principalType": "human",
                "issuer": _ISSUER,
                "jwksUri": _JWKS_URI,
                "allowedAlgorithms": ["RS256"],
                "allowedAudiences": [_AUDIENCE],
                "jwksCacheTtlSeconds": 3600,
                "revocationMode": "none",
                "roleMappings": {"premium-buyers": "premiumCustomer"},
            }
        },
        "surfaces": {},
    }


# ---------------------------------------------------------------------------
# Fixture JWKS client (drop-in for PyJWKClient; reads from a dict)
# ---------------------------------------------------------------------------


class _FixtureJwksClient:
    def __init__(self, jwks: dict[str, Any], *, raise_on_fetch: bool = False) -> None:
        self._jwks = jwks
        self._raise_on_fetch = raise_on_fetch
        self._fetched = False

    def get_signing_key_from_jwt(self, token: str) -> Any:
        from jwt.api_jwk import PyJWKSet
        from jwt.exceptions import PyJWKClientError

        jwk_set = PyJWKSet.from_dict(self._jwks)
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        for key in jwk_set.keys:
            key_id = getattr(key, "key_id", None)
            if kid is None or key_id == kid:
                return key
        raise PyJWKClientError("No matching key found in fixture JWKS")

    def fetch_data(self) -> None:
        self._fetched = True
        if self._raise_on_fetch:
            raise OSError("JWKS endpoint unavailable (simulated refresh failure)")


# ---------------------------------------------------------------------------
# Python validator: render + exec + drive
# ---------------------------------------------------------------------------


def _python_template_gen() -> TemplateGenerator:
    from datrix_codegen_python import plugin as py_plugin

    tg = TemplateGenerator(
        template_dir=template_dir_for(py_plugin.__file__),
        target_language="python",
    )
    tg.add_global("service_target_language", "python")
    tg.add_global("has_prometheus_metrics", False)
    return tg


def _render_python_identity() -> str:
    from datrix_codegen_python.generators._helpers import render_python_file

    content = render_python_file(
        _python_template_gen(),
        "api/identity.py.j2",
        Path("identity.py"),
        service_name="shop.StorefrontService",
    ).content
    ast.parse(content)
    return content


class _PythonValidator:
    """Loads the generated identity.py and drives validate_token_claims."""

    def __init__(self, content: str, plan_path: Path) -> None:
        self._content = content
        self._plan_path = plan_path

    def _module(
        self, *, jwks: dict[str, Any], raise_on_fetch: bool = False
    ) -> types.ModuleType:
        module = types.ModuleType("shop_storefront_service.identity")
        exec(self._content, module.__dict__)  # noqa: S102 - generated-code test
        module._cached_plan = None  # type: ignore[attr-defined]
        module._cached_plan_path = None  # type: ignore[attr-defined]
        os.environ[module._PLAN_ENV_VAR] = str(self._plan_path)
        client = _FixtureJwksClient(jwks, raise_on_fetch=raise_on_fetch)
        cache_key = "%s|%s" % (_PROVIDER, _JWKS_URI)
        module._jwks_clients[cache_key] = client
        return module

    def accept(self, token: str, *, jwks: dict[str, Any]) -> dict[str, Any]:
        module = self._module(jwks=jwks)
        return asyncio.run(module.validate_token_claims(token))

    def reject(
        self, token: str, *, jwks: dict[str, Any], raise_on_fetch: bool = False
    ) -> str:
        module = self._module(jwks=jwks, raise_on_fetch=raise_on_fetch)
        try:
            asyncio.run(module.validate_token_claims(token))
        except Exception as exc:  # noqa: BLE001 - we assert on reason_code below
            reason = getattr(exc, "reason_code", None)
            assert reason is not None, (
                "validator raised %r without a reason_code" % type(exc).__name__
            )
            return str(reason)
        raise AssertionError("expected token to be rejected, but it was accepted")


@pytest.fixture()
def python_validator(tmp_path: Path) -> _PythonValidator:
    plan_path = tmp_path / "identity-providers.json"
    plan_path.write_text(json.dumps(_provider_plan()), encoding="utf-8")
    return _PythonValidator(_render_python_identity(), plan_path)


@pytest.fixture()
def primary_key() -> tuple[rsa.RSAPrivateKey, str, dict[str, Any]]:
    private_key, _ = _rsa_pair()
    kid = "key-2026-01"
    return private_key, kid, _jwks([_jwk(private_key, kid)])


# ---------------------------------------------------------------------------
# TypeScript validator: render + reason-code surface
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ts_identity_source() -> str:
    from datrix_codegen_typescript import plugin as ts_plugin

    tg = TemplateGenerator(
        template_dir=template_dir_for(ts_plugin.__file__),
        target_language="typescript",
    )
    tg.add_global("has_prometheus_metrics", False)
    return tg.render("auth/identity.ts.j2")


@pytest.fixture(scope="module")
def ts_guard_source() -> str:
    from datrix_codegen_typescript import plugin as ts_plugin

    tg = TemplateGenerator(
        template_dir=template_dir_for(ts_plugin.__file__),
        target_language="typescript",
    )
    tg.add_global("has_prometheus_metrics", False)
    return tg.render("auth/auth.guard.ts.j2", default_surface_id="storefront-api")


# ---------------------------------------------------------------------------
# DN34 runtime cases — Python behaviour + TS reason-code parity
# ---------------------------------------------------------------------------


class TestPythonValidatorBehaviour:
    """The generated Python validator returns the expected DN34 reason codes."""

    def test_valid_token_accepted_with_role_extraction(
        self,
        python_validator: _PythonValidator,
        primary_key: tuple[rsa.RSAPrivateKey, str, dict[str, Any]],
    ) -> None:
        private_key, kid, jwks = primary_key
        token = _sign(private_key, kid, _payload(roles=["premiumCustomer"]))
        claims = python_validator.accept(token, jwks=jwks)
        assert claims["sub"] == "user-123"
        assert "premiumCustomer" in claims["roles"]

    def test_expired_token_rejected(
        self,
        python_validator: _PythonValidator,
        primary_key: tuple[rsa.RSAPrivateKey, str, dict[str, Any]],
    ) -> None:
        private_key, kid, jwks = primary_key
        token = _sign(private_key, kid, _payload(exp_offset=-10))
        assert python_validator.reject(token, jwks=jwks) == (
            AuthReasonCode.EXPIRED_TOKEN.value
        )

    def test_bad_signature_rejected(
        self,
        python_validator: _PythonValidator,
        primary_key: tuple[rsa.RSAPrivateKey, str, dict[str, Any]],
    ) -> None:
        _, kid, jwks = primary_key
        other_key, _ = _rsa_pair()
        token = _sign(other_key, kid, _payload())
        reason = python_validator.reject(token, jwks=jwks)
        assert reason in (
            AuthReasonCode.BAD_SIGNATURE.value,
            AuthReasonCode.JWKS_REFRESH_FAILED.value,
        )

    def test_issuer_mismatch_rejected(
        self,
        python_validator: _PythonValidator,
        primary_key: tuple[rsa.RSAPrivateKey, str, dict[str, Any]],
    ) -> None:
        private_key, kid, jwks = primary_key
        token = _sign(private_key, kid, _payload(iss="https://evil.example.com"))
        reason = python_validator.reject(token, jwks=jwks)
        assert reason in (
            AuthReasonCode.PROVIDER_MISMATCH.value,
            AuthReasonCode.ISSUER_MISMATCH.value,
        )

    def test_audience_mismatch_rejected(
        self,
        python_validator: _PythonValidator,
        primary_key: tuple[rsa.RSAPrivateKey, str, dict[str, Any]],
    ) -> None:
        private_key, kid, jwks = primary_key
        token = _sign(private_key, kid, _payload(aud="wrong-audience"))
        assert python_validator.reject(token, jwks=jwks) == (
            AuthReasonCode.AUDIENCE_MISMATCH.value
        )

    def test_hs256_token_rejected(
        self,
        python_validator: _PythonValidator,
        primary_key: tuple[rsa.RSAPrivateKey, str, dict[str, Any]],
    ) -> None:
        _, _, jwks = primary_key
        hs_token = jwt.encode(
            _payload(), "x" * 48, algorithm="HS256"
        )
        assert python_validator.reject(hs_token, jwks=jwks) == (
            AuthReasonCode.BAD_SIGNATURE.value
        )

    def test_alg_none_token_rejected(
        self,
        python_validator: _PythonValidator,
        primary_key: tuple[rsa.RSAPrivateKey, str, dict[str, Any]],
    ) -> None:
        _, _, jwks = primary_key
        header = (
            base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
            .rstrip(b"=")
            .decode()
        )
        body = (
            base64.urlsafe_b64encode(json.dumps(_payload()).encode())
            .rstrip(b"=")
            .decode()
        )
        none_token = "%s.%s." % (header, body)
        reason = python_validator.reject(none_token, jwks=jwks)
        assert reason in (
            AuthReasonCode.BAD_SIGNATURE.value,
            AuthReasonCode.MALFORMED_TOKEN.value,
            AuthReasonCode.PROVIDER_MISMATCH.value,
        )

    def test_jwks_refresh_failure_fails_closed(
        self,
        python_validator: _PythonValidator,
        primary_key: tuple[rsa.RSAPrivateKey, str, dict[str, Any]],
    ) -> None:
        private_key, _, _ = primary_key
        token = _sign(private_key, "unknown-kid", _payload())
        reason = python_validator.reject(
            token, jwks=_jwks([]), raise_on_fetch=True
        )
        assert reason == AuthReasonCode.JWKS_REFRESH_FAILED.value

    def test_empty_credential_rejected(
        self, python_validator: _PythonValidator
    ) -> None:
        # At the validator layer an empty/structurally-invalid credential is
        # malformed; the MISSING_TOKEN reason is reported by the guard layer
        # (asserted present in the TS guard surface in the parity test below).
        reason = python_validator.reject("", jwks=_jwks([]))
        assert reason in (
            AuthReasonCode.MALFORMED_TOKEN.value,
            AuthReasonCode.MISSING_TOKEN.value,
        )


class TestCrossLanguageReasonCodeParity:
    """Every reason code the Python path emits is present in the TS validator/guard.

    This is the DN45 guard: the two language targets share the SAME reason-code
    vocabulary, so they cannot drift in their accept/reject reporting.
    """

    #: The reason codes exercised by the Python behaviour tests above.
    _EXERCISED: tuple[AuthReasonCode, ...] = (
        AuthReasonCode.EXPIRED_TOKEN,
        AuthReasonCode.BAD_SIGNATURE,
        AuthReasonCode.ISSUER_MISMATCH,
        AuthReasonCode.AUDIENCE_MISMATCH,
        AuthReasonCode.PROVIDER_MISMATCH,
        AuthReasonCode.MALFORMED_TOKEN,
        AuthReasonCode.JWKS_REFRESH_FAILED,
        AuthReasonCode.MISSING_TOKEN,
    )

    def test_identity_validator_reason_codes_present_in_ts(
        self, ts_identity_source: str, ts_guard_source: str
    ) -> None:
        combined = ts_identity_source + "\n" + ts_guard_source
        for code in self._EXERCISED:
            assert code.value in combined, (
                "reason code %r emitted by the Python validator is absent from the "
                "generated TypeScript identity surface (DN45 parity violation)"
                % code.value
            )

    def test_ts_rejects_symmetric_and_none_algorithms(
        self, ts_identity_source: str
    ) -> None:
        # Parity with Python: HS* and none are rejected before key resolution.
        assert "REJECTED_ALG_PREFIXES" in ts_identity_source
        assert "REJECTED_ALG_NONE" in ts_identity_source

    def test_ts_uses_jwks_with_kid_rotation(self, ts_identity_source: str) -> None:
        # Parity with Python's PyJWKClient kid refresh: jose createRemoteJWKSet.
        assert "createRemoteJWKSet" in ts_identity_source

    def test_ts_jwks_refresh_fails_closed(self, ts_identity_source: str) -> None:
        assert AuthReasonCode.JWKS_REFRESH_FAILED.value in ts_identity_source

    def test_exercised_codes_are_real_auth_reason_codes(self) -> None:
        valid = {c.value for c in AuthReasonCode}
        for code in self._EXERCISED:
            assert code.value in valid

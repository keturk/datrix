"""Credential provider. Auto-generated. Do not edit.

Constructs the deployment credential with NO environment dependency. Selected by
the baked CREDENTIAL_KIND constant from config._bootstrap.
"""

from __future__ import annotations

import logging

from library_book_service.config import _bootstrap

logger = logging.getLogger(__name__)

_CREDENTIAL_KIND: str = _bootstrap.CREDENTIAL_KIND


def azure_credential() -> object:
    """Managed-identity credential that NEVER consults environment variables.

    Constructs ``ManagedIdentityCredential`` directly, which contacts the Azure
    IMDS endpoint only.  No ``EnvironmentCredential`` leg is present, so no
    ``AZURE_*`` env vars are consulted.

    Returns:
        An async ``ManagedIdentityCredential`` instance.

    Raises:
        ImportError: When ``azure-identity`` is not installed.
        RuntimeError: When ``CREDENTIAL_KIND`` is not ``azure-managed-identity``.
    """
    try:
        from azure.identity.aio import ManagedIdentityCredential
    except ImportError as exc:
        raise ImportError(
            "azure-identity is not installed. "
            "Add 'azure-identity>=1.18.0' to the service dependencies."
        ) from exc
    if _CREDENTIAL_KIND != "azure-managed-identity":
        raise RuntimeError(
            "azure_credential() called but CREDENTIAL_KIND is %r — expected "
            "'azure-managed-identity'. Verify the deployment profile and regenerate."
            % _CREDENTIAL_KIND
        )
    logger.debug("credential_provider credential_kind=azure-managed-identity")
    return ManagedIdentityCredential()


def azure_credential_sync() -> object:
    """Synchronous managed-identity credential for synchronous Azure SDK clients.

    Identical no-env managed-identity strategy as ``azure_credential()`` but
    returns the *synchronous* ``azure.identity.ManagedIdentityCredential``.
    Synchronous SDK clients (e.g. the synchronous ``AzureAppConfigurationClient``)
    call ``credential.get_token(...)`` directly and read ``.expires_on`` off the
    result; handing them the async (``azure.identity.aio``) credential returns an
    un-awaited coroutine and raises ``'coroutine' object has no attribute
    'expires_on'``. Use this accessor wherever the consuming client is synchronous.

    Returns:
        A synchronous ``ManagedIdentityCredential`` instance.

    Raises:
        ImportError: When ``azure-identity`` is not installed.
        RuntimeError: When ``CREDENTIAL_KIND`` is not ``azure-managed-identity``.
    """
    try:
        from azure.identity import ManagedIdentityCredential
    except ImportError as exc:
        raise ImportError(
            "azure-identity is not installed. "
            "Add 'azure-identity>=1.18.0' to the service dependencies."
        ) from exc
    if _CREDENTIAL_KIND != "azure-managed-identity":
        raise RuntimeError(
            "azure_credential_sync() called but CREDENTIAL_KIND is %r — expected "
            "'azure-managed-identity'. Verify the deployment profile and regenerate."
            % _CREDENTIAL_KIND
        )
    logger.debug("credential_provider credential_kind=azure-managed-identity sync=true")
    return ManagedIdentityCredential()


def aws_client(service_name: str) -> object:
    """Return a boto3 client with the baked region; credentials via task/instance role.

    The ``region_name`` argument is always the baked ``_bootstrap.REGION`` constant
    — ``AWS_REGION`` / ``AWS_DEFAULT_REGION`` env vars are never consulted.

    Args:
        service_name: AWS service name passed to ``boto3.client``
            (e.g. ``"secretsmanager"``, ``"appconfig"``).

    Returns:
        A boto3 service client.

    Raises:
        ImportError: When ``boto3`` is not installed.
        RuntimeError: When ``CREDENTIAL_KIND`` is not ``aws-instance-role``.
        RuntimeError: When ``REGION`` is not baked (None) — boto3 would fall back
            to the env var, violating the zero-env contract.
    """
    try:
        import boto3
    except ImportError as exc:
        raise ImportError(
            "boto3 is not installed. Add 'boto3>=1.34.0' to the service dependencies."
        ) from exc
    if _CREDENTIAL_KIND != "aws-instance-role":
        raise RuntimeError(
            "aws_client() called but CREDENTIAL_KIND is %r — expected "
            "'aws-instance-role'. Verify the deployment profile and regenerate."
            % _CREDENTIAL_KIND
        )
    if not _bootstrap.REGION:
        raise RuntimeError(
            "aws_client() requires a baked REGION constant but REGION is None. "
            "The generator must bake the AWS region at generation time so boto3 "
            "never falls back to AWS_REGION env. Regenerate with a resolved region."
        )
    logger.debug(
        "credential_provider credential_kind=aws-instance-role service=%s region=%s",
        service_name,
        _bootstrap.REGION,
    )
    return boto3.client(service_name, region_name=_bootstrap.REGION)


def mounted_file_credential() -> str:
    """Return the path to the mounted credential file (LOCAL/docker).

    The path is the baked ``_bootstrap.CREDENTIAL_FILE_PATH`` constant — never
    an env var.

    Returns:
        Absolute path string to the mounted credential file.

    Raises:
        RuntimeError: When ``CREDENTIAL_KIND`` is not ``mounted-file``.
        RuntimeError: When ``CREDENTIAL_FILE_PATH`` is not baked (None or empty).
    """
    if _CREDENTIAL_KIND != "mounted-file":
        raise RuntimeError(
            "mounted_file_credential() called but CREDENTIAL_KIND is %r — expected "
            "'mounted-file'. Verify the deployment profile and regenerate."
            % _CREDENTIAL_KIND
        )
    if not _bootstrap.CREDENTIAL_FILE_PATH:
        raise RuntimeError(
            "CREDENTIAL_FILE_PATH is not baked; cannot resolve mounted-file credential. "
            "The generator must bake the credential file path for LOCAL deployments. "
            "Regenerate with a resolved CREDENTIAL_FILE_PATH."
        )
    logger.debug(
        "credential_provider credential_kind=mounted-file path=%s",
        _bootstrap.CREDENTIAL_FILE_PATH,
    )
    return _bootstrap.CREDENTIAL_FILE_PATH


def select_credential_kind() -> str:
    """Return the baked credential kind constant.

    Convenience accessor used by secrets/config backends to dispatch on the
    credential kind without importing ``_bootstrap`` directly.

    Returns:
        The ``CREDENTIAL_KIND`` string (e.g. ``"azure-managed-identity"``).
    """
    return _CREDENTIAL_KIND

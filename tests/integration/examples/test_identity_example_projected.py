"""Integration test: identity example exercises the explicit-profileStore projected path.

This is the canonical proof that the identity example remains a working demonstration
of the opt-in ``projected`` local-identity mode with an explicit ``profileStore``.

The ``customer`` provider in
``examples/02-features/01-core-data-modeling/identity/config/identity/customer.dcfg``
declares ``profileProjection { enabled = true; profileStore = "shop.StorefrontService"; }``.
The planner must resolve that service name to its single rdbms block (``storeDb``) and
emit a ``ProviderPlanEntry`` with:
  - ``localIdentity.mode == "projected"``
  - ``profileProjection.profileStore == "storeDb"``  (resolved rdbms block name)
  - ``profileProjection.enabled == True``

``IdentityProfile`` and ``IdentityLink`` are injected into ``storeDb`` (verified via
the injection stage exercised by the datrix-cli integration suite).

No mocks — real Application parsed from the committed example, real IdentityConfig
loaded from the committed ``.dcfg`` files.
"""

from __future__ import annotations

import pytest

from datrix_common.identity.capability_matrix import DeploymentTarget
from datrix_common.identity.local_identity import LocalIdentityMode
from datrix_common.identity.planner import IdentityPlanner
from datrix_common.testing.identity_example import (
    collect_auth_contracts,
    load_committed_configs,
    load_example_app,
)


@pytest.mark.integration
class TestIdentityExampleProjected:
    """The identity example generates with mode=projected and explicit profileStore."""

    def test_customer_provider_local_identity_mode_is_projected(self) -> None:
        """customer provider resolves to localIdentity.mode == projected.

        The committed customer.dcfg declares profileProjection { enabled = true }
        with an explicit profileStore, so the planner must emit mode=projected.
        """
        app = load_example_app()
        configs = load_committed_configs()
        contracts = collect_auth_contracts(app)

        planner = IdentityPlanner(
            app,
            environment="test",
            deployment_target=DeploymentTarget.DOCKER,
            provider_configs=configs,
            auth_contracts=contracts,
            owning_service=None,
        )

        plan = planner.build_plan()
        entry = plan.providers["customer"]

        assert entry.local_identity.mode is LocalIdentityMode.PROJECTED, (
            "customer provider must resolve to projected mode; "
            "profileProjection.enabled=true is declared in customer.dcfg. "
            "Got mode=%r" % entry.local_identity.mode
        )

    def test_customer_provider_profile_projection_present(self) -> None:
        """customer provider plan entry carries a non-None profileProjection block."""
        app = load_example_app()
        configs = load_committed_configs()
        contracts = collect_auth_contracts(app)

        planner = IdentityPlanner(
            app,
            environment="test",
            deployment_target=DeploymentTarget.DOCKER,
            provider_configs=configs,
            auth_contracts=contracts,
            owning_service=None,
        )

        plan = planner.build_plan()
        entry = plan.providers["customer"]

        assert entry.profile_projection is not None, (
            "customer provider must carry a profileProjection block in the plan; "
            "profileProjection.enabled=true is declared in customer.dcfg."
        )
        assert entry.profile_projection.enabled is True, (
            "profileProjection.enabled must be True in the emitted plan."
        )

    def test_customer_provider_profile_store_resolves_to_rdbms_block(self) -> None:
        """profileProjection.profileStore in the plan equals the resolved rdbms block name.

        The committed customer.dcfg declares profileStore = "shop.StorefrontService".
        The planner resolves that service name to its single rdbms block (storeDb)
        and writes the block name — not the service name — into the plan.
        """
        app = load_example_app()
        configs = load_committed_configs()
        contracts = collect_auth_contracts(app)

        planner = IdentityPlanner(
            app,
            environment="test",
            deployment_target=DeploymentTarget.DOCKER,
            provider_configs=configs,
            auth_contracts=contracts,
            owning_service=None,
        )

        plan = planner.build_plan()
        entry = plan.providers["customer"]

        assert entry.profile_projection is not None
        assert entry.profile_projection.profile_store == "storeDb", (
            "profileProjection.profileStore in the plan must equal the resolved "
            "rdbms block name 'storeDb'; got %r.  "
            "Ensure customer.dcfg declares profileStore = \"shop.StorefrontService\" "
            "and that the StorefrontService has exactly one rdbms block named storeDb."
            % entry.profile_projection.profile_store
        )

    def test_workforce_and_machine_providers_not_projected(self) -> None:
        """workforce and platformMachine providers use deterministicUuid5 (not projected).

        Only customer opts into projection; the other two providers get the
        deterministic default automatically, proving the default path is exercised too.
        """
        app = load_example_app()
        configs = load_committed_configs()
        contracts = collect_auth_contracts(app)

        planner = IdentityPlanner(
            app,
            environment="test",
            deployment_target=DeploymentTarget.DOCKER,
            provider_configs=configs,
            auth_contracts=contracts,
            owning_service=None,
        )

        plan = planner.build_plan()

        for provider_name in ("workforce", "platformMachine"):
            entry = plan.providers[provider_name]
            assert entry.local_identity.mode is not LocalIdentityMode.PROJECTED, (
                "Provider '%s' must not be projected; only customer opts in. "
                "Got mode=%r" % (provider_name, entry.local_identity.mode)
            )
            assert entry.profile_projection is None, (
                "Provider '%s' must have no profileProjection block in the plan; "
                "it does not declare profileProjection.enabled=true. "
                "Got profileProjection=%r" % (provider_name, entry.profile_projection)
            )

    def test_build_plan_succeeds_without_generation_error(self) -> None:
        """The example generates successfully — no GenerationError.

        This is the dual-path proof: explicit profileStore resolves correctly
        end-to-end through the fail-loud _select_profile_store path.
        """
        app = load_example_app()
        configs = load_committed_configs()
        contracts = collect_auth_contracts(app)

        planner = IdentityPlanner(
            app,
            environment="test",
            deployment_target=DeploymentTarget.DOCKER,
            provider_configs=configs,
            auth_contracts=contracts,
            owning_service=None,
        )

        # Must not raise GenerationError.
        plan = planner.build_plan()

        assert "customer" in plan.providers, (
            "customer provider must be present in the built plan. "
            "Got providers: %s" % sorted(plan.providers)
        )

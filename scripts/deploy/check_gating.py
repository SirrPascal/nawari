#!/usr/bin/env python3
"""scripts/deploy/check_gating.py
================================
Pre-Deployment Safety & Commissioning Gate Verifier (Stage C).

Enforces HARD_PRODUCTION_DENY policy via services.multisite.packaging.
Prevents unauthorized or uncertified deployment to production profiles.
"""

import argparse
import os
import sys

from services.multisite.packaging import (
    DeploymentProfileManager,
    ProductionGatingViolation,
)


def evaluate_gating(profile_name: str, phase_8_2_certified: bool) -> int:
    manager = DeploymentProfileManager()

    print("==================================================================")
    print("NAWARI DEPLOYMENT GATING EVALUATION (STAGE C)")
    print(f"Target Profile:          {profile_name}")
    print(f"Phase 8.2 Certified:     {phase_8_2_certified}")
    print("==================================================================")

    try:
        decision = manager.validate_deployment_eligibility(
            profile_name=profile_name,
            is_phase_8_2_certified=phase_8_2_certified,
        )
    except FileNotFoundError as err:
        print(f"[ERROR] Deployment profile not found: {err}", file=sys.stderr)
        return 1

    if not decision.get("allowed", False):
        print(f"\n[DEPLOYMENT BLOCKED — {decision.get('status')}]")
        print(f"Reason:        {decision.get('reason')}")
        print(f"Required Gate: {decision.get('required_gate')}")
        print("\nProduction deployment halted fail-closed. No containers were modified.")
        return 2

    print(f"\n[DEPLOYMENT ELIGIBILITY CONFIRMED — {decision.get('status')}]")
    print(f"Tier:                  {decision.get('tier')}")
    print(f"Live Mutation Allowed: {decision.get('live_mutation_allowed')}")
    print("Gating evaluation passed. Proceeding with deployment pipeline.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify deployment eligibility and enforce HARD_PRODUCTION_DENY"
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("NAWARI_PROFILE", "staging"),
        help="Target deployment profile (staging, single-site-production, simulation)",
    )
    parser.add_argument(
        "--phase-8-2-certified",
        action="store_true",
        default=os.getenv("PHASE_8_2_CERTIFIED", "false").lower() in ("true", "1", "yes"),
        help="Assert that Phase 8.2 physical commissioning is certified",
    )

    args = parser.parse_args()
    sys.exit(evaluate_gating(args.profile, args.phase_8_2_certified))


if __name__ == "__main__":
    main()


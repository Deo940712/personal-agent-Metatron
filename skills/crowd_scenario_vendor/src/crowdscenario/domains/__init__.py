"""Domain packs: the pluggable persona/axis/vocabulary bundles the engine reads.

The core engine is domain-agnostic. Everything that used to be Taiwan-stock
specific — the persona roster, their voices, the ordinal axes and their buckets —
lives in a ``DomainPack`` (see ``base.py``). A pack is an explicit, frozen object
passed into ``make_seed``/``run_scenario``; there is no global registry.

The firewall is unchanged: a pack only supplies *categorical* material. It cannot
introduce a numeric scalar into an emitted artifact, and ``validate_pack`` refuses
any pack whose parallel tables are misaligned.
"""

from __future__ import annotations

from crowdscenario.domains.base import Axis, DomainPack, validate_pack

__all__ = ["Axis", "DomainPack", "validate_pack"]

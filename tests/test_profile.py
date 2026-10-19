"""The CyberAware profile loads through AIGoat's own validator and changes only rag.kb L2."""
from __future__ import annotations

import yaml

from app.defense.profiles import load_defense_profiles, resolve_profile

from conftest import AIGOAT_DIR, PROFILE


def test_profile_passes_aigoat_validation():
    profiles = load_defense_profiles()  # raises on unknown ids or a non-empty L0
    assert profiles


def test_rag_kb_level_2_runs_trust_gate_after_acl():
    controls = resolve_profile("rag.kb", 2).controls
    assert "cyberaware.trust_gate" in controls
    assert controls.index("retrieval.acl") < controls.index("cyberaware.trust_gate")
    assert controls.index("cyberaware.trust_gate") < controls.index("retrieval.injection_scan")


def test_only_rag_kb_level_2_differs_from_stock():
    ours = yaml.safe_load(PROFILE.read_text())["profiles"]
    stock = yaml.safe_load((AIGOAT_DIR / "config" / "defense_profiles.yml").read_text())["profiles"]
    assert ours.keys() == stock.keys()
    for surface, levels in stock.items():
        for level, body in levels.items():
            if (surface, level) == ("rag.kb", 2):
                continue
            assert ours[surface][level]["controls"] == body["controls"], (surface, level)

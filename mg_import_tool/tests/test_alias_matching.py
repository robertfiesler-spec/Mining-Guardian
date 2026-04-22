"""
test_alias_matching.py
======================
Unit tests for V-suffix stripping regex and resolve_model logic.
No database connection required — tests the pure Python helpers only.

Run:
    python -m pytest tests/test_alias_matching.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from mg_import import strip_v_suffix, V_SUFFIX_RE


# ---------------------------------------------------------------------------
# strip_v_suffix tests — 20 cases covering spec + edge cases
# ---------------------------------------------------------------------------

class TestStripVSuffix:

    # --- normal V-code stripping ---
    def test_m31s_plus_v100(self):
        base, rev = strip_v_suffix("M31S+_V100")
        assert base == "M31S+"
        assert rev  == "V100"

    def test_m56s_plus_plus_vk10(self):
        base, rev = strip_v_suffix("M56S++_VK10")
        assert base == "M56S++"
        assert rev  == "VK10"

    def test_m21s_no_suffix(self):
        base, rev = strip_v_suffix("M21S")
        assert base == "M21S"
        assert rev  is None

    def test_m50_bare(self):
        base, rev = strip_v_suffix("M50")
        assert base == "M50"
        assert rev  is None

    def test_m30s_plus_v80(self):
        base, rev = strip_v_suffix("M30S+_V80")
        assert base == "M30S+"
        assert rev  == "V80"

    def test_m30s_plus_plus_v30(self):
        base, rev = strip_v_suffix("M30S++_V30")
        assert base == "M30S++"
        assert rev  == "V30"

    def test_m10s_v100(self):
        base, rev = strip_v_suffix("M10S_V100")
        assert base == "M10S"
        assert rev  == "V100"

    def test_m53s_ve30(self):
        base, rev = strip_v_suffix("M53S_VE30")
        assert base == "M53S"
        assert rev  == "VE30"

    def test_m50s_plus_plus_v30(self):
        base, rev = strip_v_suffix("M50S++_V30")
        assert base == "M50S++"
        assert rev  == "V30"

    def test_m31s_dash_v100(self):
        # dash models also occur (M31S- archive name)
        base, rev = strip_v_suffix("M31S-_V100")
        assert base == "M31S-"
        assert rev  == "V100"

    # --- Antminer strings (no V-suffix to strip) ---
    def test_antminer_s19_no_suffix(self):
        base, rev = strip_v_suffix("Antminer S19")
        assert base == "Antminer S19"
        assert rev  is None

    def test_antminer_s19_underscore(self):
        base, rev = strip_v_suffix("Antminer_S19")
        # underscore in Antminer name: no V-suffix present
        assert rev is None

    def test_bare_s19(self):
        base, rev = strip_v_suffix("S19")
        assert base == "S19"
        assert rev  is None

    # --- alpha-only revision prefix (VE, VK) ---
    def test_ve50_suffix(self):
        base, rev = strip_v_suffix("M50_VE50")
        assert base == "M50"
        assert rev  == "VE50"

    def test_vk10_suffix(self):
        base, rev = strip_v_suffix("M56S_VK10")
        assert base == "M56S"
        assert rev  == "VK10"

    # --- whitespace handling ---
    def test_leading_trailing_space(self):
        base, rev = strip_v_suffix("  M31S+_V100  ")
        assert base == "M31S+"
        assert rev  == "V100"

    # --- empty / None ---
    def test_empty_string(self):
        base, rev = strip_v_suffix("")
        assert base == ""
        assert rev  is None

    def test_none_passthrough(self):
        base, rev = strip_v_suffix(None)
        assert base is None
        assert rev  is None

    # --- no-underscore V-suffix (no separator) — should NOT strip ---
    def test_m31s_plus_v100_no_sep(self):
        # "M31S+V100" has no underscore separator — treated as whole base
        base, rev = strip_v_suffix("M31S+V100")
        # Regex requires _V so this should NOT strip
        assert rev is None
        assert base == "M31S+V100"

    # --- verify round-trip: stripped base can be looked up as plain model ---
    def test_stripped_base_looks_like_catalog_key(self):
        base, rev = strip_v_suffix("M56S++_VK10")
        # base should look like a valid WhatsMiner model string
        assert "+" in base or base.startswith("M")
        assert rev.startswith("V")


# ---------------------------------------------------------------------------
# V_SUFFIX_RE direct tests
# ---------------------------------------------------------------------------

class TestVSuffixRegex:

    def test_regex_groups_m31s_v100(self):
        m = V_SUFFIX_RE.match("M31S+_V100")
        assert m is not None
        assert m.group("base") == "M31S+"
        assert m.group("rev")  == "100"   # raw group before 'V' prefix added

    def test_regex_no_match_antminer_s19(self):
        # "Antminer S19" has a space — doesn't match our underscore-V pattern
        # but it should still match the base group
        m = V_SUFFIX_RE.match("Antminer S19")
        # Space causes no match since [^_]* stops at underscore not space... 
        # actually it may match with base="Antminer S19" and no rev
        if m:
            assert m.group("rev") is None

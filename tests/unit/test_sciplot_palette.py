"""Tests for abi.sciplot.schema.palette_spec — PaletteRegistry and palette models."""

from __future__ import annotations

import pytest
import yaml

from abi.sciplot.schema.palette_spec import (
    FORBIDDEN_PALETTES,
    FORBIDDEN_SUBSTRINGS,
    CategoricalPalette,
    ContinuousPalette,
    DivergingPalette,
    PaletteRegistry,
)

# ── CategoricalPalette model ─────────────────────────────────────────────


def test_categorical_palette_construction():
    p = CategoricalPalette(
        name="my_pal",
        type="categorical",
        max_categories=6,
        colors=["#111111", "#222222", "#333333", "#444444", "#555555", "#666666"],
        source="test",
    )
    assert p.name == "my_pal"
    assert p.max_categories == 6
    assert len(p.colors) == 6


def test_continuous_palette_construction():
    p = ContinuousPalette(name="viridis", type="continuous", source="matplotlib")
    assert p.name == "viridis"
    assert p.source == "matplotlib"


def test_diverging_palette_construction():
    p = DivergingPalette(name="coolwarm", type="diverging", source="matplotlib")
    assert p.name == "coolwarm"
    assert p.source == "matplotlib"


# ── Registration — forbidden names ──────────────────────────────────────


def test_register_rejects_exact_forbidden_name():
    """register raises ValueError when palette name is in FORBIDDEN_PALETTES."""
    registry = PaletteRegistry()
    for name in sorted(FORBIDDEN_PALETTES)[:2]:  # Test a couple to be safe
        with pytest.raises(ValueError, match="forbidden"):
            registry.register(ContinuousPalette(name=name, type="continuous", source="test"))


def test_register_rejects_forbidden_substring():
    """register raises ValueError when palette name contains a forbidden substring."""
    registry = PaletteRegistry()
    for substr in FORBIDDEN_SUBSTRINGS:
        with pytest.raises(
            ValueError,
            match=r"matches forbidden pattern|forbidden",
        ):
            registry.register(
                ContinuousPalette(name=f"my_{substr}_pal", type="continuous", source="test")
            )


def test_register_accepts_valid_palettes():
    """Valid palette names are registered into the correct internal dict."""
    registry = PaletteRegistry()
    registry.register(
        CategoricalPalette(
            name="my_cat",
            type="categorical",
            max_categories=5,
            colors=["#111111", "#222222", "#333333", "#444444", "#555555"],
        )
    )
    registry.register(ContinuousPalette(name="my_seq", type="continuous", source="test"))
    registry.register(DivergingPalette(name="my_div", type="diverging", source="test"))

    assert "my_cat" in registry._categorical
    assert "my_seq" in registry._continuous
    assert "my_div" in registry._diverging


# ── from_yaml ────────────────────────────────────────────────────────────


def test_from_yaml_reads_qualitative_sequential_diverging(tmp_path):
    yaml_content = {
        "qualitative": {
            "test_cat": {
                "colors": ["#FF0000", "#00FF00", "#0000FF"],
                "max_categories": 3,
                "source": "yaml_test",
            },
        },
        "sequential": {
            "test_seq": {"source": "yaml_test"},
        },
        "diverging": {
            "test_div": {"source": "yaml_test"},
        },
    }
    yaml_path = tmp_path / "palettes.yaml"
    yaml_path.write_text(yaml.dump(yaml_content))

    registry = PaletteRegistry.from_yaml(yaml_path)
    assert "test_cat" in registry.categorical_names
    assert "test_seq" in registry.continuous_names
    assert "test_div" in registry.diverging_names


def test_from_yaml_handles_non_dict_sections(tmp_path):
    """Non-dict sections are silently skipped."""
    yaml_content = {
        "qualitative": "not_a_dict",
        "sequential": {
            "test_seq": {"source": "yaml_test"},
        },
    }
    yaml_path = tmp_path / "palettes.yaml"
    yaml_path.write_text(yaml.dump(yaml_content))

    registry = PaletteRegistry.from_yaml(yaml_path)
    assert registry.categorical_names == set()
    assert "test_seq" in registry.continuous_names


# ── get_categorical ─────────────────────────────────────────────────────


def test_get_categorical_fallback_to_colorblind_safe_8():
    """Unknown name → fallback to colorblind_safe_8 (when registered)."""
    registry = PaletteRegistry()
    registry.load_builtins()
    colors = registry.get_categorical("nonexistent", n=4)
    assert len(colors) == 4
    assert colors == PaletteRegistry.COLORBLIND_SAFE_8[:4]


def test_get_categorical_ultimate_fallback_to_classvar():
    """When even colorblind_safe_8 is not registered, fall back to class var."""
    registry = PaletteRegistry()
    # No palettes registered at all
    colors = registry.get_categorical("anything", n=3)
    assert colors == PaletteRegistry.COLORBLIND_SAFE_8[:3]


def test_get_categorical_n_exceeds_max_raises():
    """Requesting more categories than max_categories → ValueError."""
    registry = PaletteRegistry()
    registry.register(
        CategoricalPalette(
            name="small",
            type="categorical",
            max_categories=4,
            colors=["#111111", "#222222", "#333333", "#444444"],
        )
    )
    with pytest.raises(ValueError, match="4 categories"):
        registry.get_categorical("small", n=8)


# ── get_continuous ──────────────────────────────────────────────────────


def test_get_continuous_found():
    registry = PaletteRegistry()
    registry.register(ContinuousPalette(name="magma", type="continuous", source="test"))
    assert registry.get_continuous("magma") == "magma"


def test_get_continuous_fallback_to_viridis():
    """Unknown continuous name → fallback to 'viridis'."""
    registry = PaletteRegistry()
    assert registry.get_continuous("nonexistent") == "viridis"


# ── get_diverging ───────────────────────────────────────────────────────


def test_get_diverging_found():
    registry = PaletteRegistry()
    registry.register(DivergingPalette(name="coolwarm", type="diverging", source="test"))
    assert registry.get_diverging("coolwarm") == "coolwarm"


def test_get_diverging_fallback_to_coolwarm():
    """Unknown diverging name → fallback to 'coolwarm'."""
    registry = PaletteRegistry()
    assert registry.get_diverging("nonexistent") == "coolwarm"


# ── get_matplotlib_colormap ─────────────────────────────────────────────


def test_get_matplotlib_colormap_found():
    registry = PaletteRegistry()
    registry.register(ContinuousPalette(name="inferno", type="continuous", source="test"))
    registry.register(DivergingPalette(name="vik", type="diverging", source="test"))

    assert registry.get_matplotlib_colormap("inferno") == "inferno"
    assert registry.get_matplotlib_colormap("vik") == "vik"


def test_get_matplotlib_colormap_not_found_default():
    """Not found → default to viridis (when diverging_default=False)."""
    registry = PaletteRegistry()
    assert registry.get_matplotlib_colormap("zzz") == "viridis"


def test_get_matplotlib_colormap_not_found_diverging_default():
    """Not found with diverging_default=True → coolwarm."""
    registry = PaletteRegistry()
    assert registry.get_matplotlib_colormap("zzz", diverging_default=True) == "coolwarm"


# ── Properties ──────────────────────────────────────────────────────────


def test_categorical_names_property():
    registry = PaletteRegistry()
    registry.load_builtins()
    assert "colorblind_safe_8" in registry.categorical_names
    assert "magma" not in registry.categorical_names  # continuous


def test_continuous_names_property():
    registry = PaletteRegistry()
    registry.load_builtins()
    assert "viridis" in registry.continuous_names
    assert "magma" in registry.continuous_names


def test_diverging_names_property():
    registry = PaletteRegistry()
    registry.load_builtins()
    assert "coolwarm" in registry.diverging_names
    assert "vik" in registry.diverging_names


def test_load_builtins_populates_all_lists():
    registry = PaletteRegistry()
    registry.load_builtins()
    assert len(registry.categorical_names) >= 1
    assert len(registry.continuous_names) >= 5
    assert len(registry.diverging_names) >= 2


# ── is_allowed ──────────────────────────────────────────────────────────


def test_is_allowed_forbidden_exact_name():
    """is_allowed returns False for exact forbidden names."""
    registry = PaletteRegistry()
    for name in FORBIDDEN_PALETTES:
        assert registry.is_allowed(name) is False


def test_is_allowed_forbidden_substring():
    registry = PaletteRegistry()
    assert registry.is_allowed("my_rainbow_palette") is False
    assert registry.is_allowed("jet_plus") is False


def test_is_allowed_registered_palette():
    registry = PaletteRegistry()
    registry.load_builtins()
    assert registry.is_allowed("viridis") is True
    assert registry.is_allowed("colorblind_safe_8") is True
    assert registry.is_allowed("coolwarm") is True


def test_is_allowed_unknown_but_not_forbidden():
    """Not registered, not forbidden → False."""
    registry = PaletteRegistry()
    assert registry.is_allowed("some_unknown_palette") is False

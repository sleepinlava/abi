"""PaletteSpec — safe, perceptually uniform colour palettes for scientific figures.

Design rules / 设计规则:
- Qualitative (categorical) palettes: ≤8 colours, colourblind-safe (Wong 2011).
- Sequential palettes: perceptually uniform (viridis, batlow, etc.).
- Diverging palettes: must have a meaningful centre point.
- **Hard ban**: jet, rainbow, and any red-green-only contrast palettes.

References:
- Wong, B. (2011). Points of view: Color blindness. Nature Methods.
- Crameri, F. et al. (2020). The misuse of colour in science communication. Nature Comms.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Dict, Optional, Set

import yaml
from pydantic import BaseModel, Field

# ── Forbidden palettes / 禁用调色板 ──────────────────────────────────────

FORBIDDEN_PALETTES: frozenset[str] = frozenset(
    {
        "jet",
        "rainbow",
        "hsv",
        "gist_rainbow",
        "gist_ncar",
        "nipy_spectral",
        "turbo",
    }
)

FORBIDDEN_SUBSTRINGS: tuple[str, ...] = ("jet", "rainbow", "turbo")


# ── Palette models / 调色板模型 ──────────────────────────────────────────


class CategoricalPalette(BaseModel):
    """Qualitative palette for categorical data.

    Limited to max_categories to prevent unreadable plots.
    """

    name: str = Field(..., description="Palette identifier.")
    type: str = Field("categorical", description="Palette type discriminator.")
    max_categories: int = Field(8, ge=2, le=50, description="Maximum categories supported.")
    colors: list[str] = Field(..., description="Hex colour codes.")
    source: Optional[str] = Field(None, description="Provenance of the palette.")


class ContinuousPalette(BaseModel):
    """Sequential palette for continuous data."""

    name: str = Field(..., description="Palette identifier.")
    type: str = Field("continuous", description="Palette type discriminator.")
    source: str = Field(..., description="Provenance: 'matplotlib' or 'scientific_colour_maps'.")


class DivergingPalette(BaseModel):
    """Diverging palette for data with a meaningful midpoint."""

    name: str = Field(..., description="Palette identifier.")
    type: str = Field("diverging", description="Palette type discriminator.")
    source: str = Field(..., description="Provenance: 'matplotlib' or 'scientific_colour_maps'.")


PaletteSpec = CategoricalPalette | ContinuousPalette | DivergingPalette


# ── Registry / 注册表 ────────────────────────────────────────────────────


class PaletteRegistry:
    """Central registry of approved colour palettes.

    Loads palette definitions from YAML files and provides validation
    and lookup.  Rejects forbidden palettes at registration time.

    Usage:
        registry = PaletteRegistry()
        registry.load_builtins()
        colors = registry.get_categorical("colorblind_safe_8", n=5)
    """

    # Default colourblind-safe palette (Wong 2011, Nature Methods)
    COLORBLIND_SAFE_8: ClassVar[list[str]] = [
        "#0072B2",  # blue
        "#E69F00",  # orange
        "#009E73",  # bluish green
        "#CC79A7",  # reddish purple
        "#56B4E9",  # sky blue
        "#D55E00",  # vermillion
        "#F0E442",  # yellow
        "#000000",  # black
    ]

    def __init__(self) -> None:
        self._categorical: Dict[str, CategoricalPalette] = {}
        self._continuous: Dict[str, ContinuousPalette] = {}
        self._diverging: Dict[str, DivergingPalette] = {}

    # ── Registration / 注册 ─────────────────────────────────────────────

    def register(self, palette: PaletteSpec) -> None:
        """Register a palette, checking for forbidden names."""
        name_lower = palette.name.lower()
        if name_lower in FORBIDDEN_PALETTES:
            raise ValueError(
                f"Palette '{palette.name}' is forbidden for ABI publication figures. "
                f"Forbidden palettes: {sorted(FORBIDDEN_PALETTES)}"
            )
        for substr in FORBIDDEN_SUBSTRINGS:
            if substr in name_lower:
                raise ValueError(
                    f"Palette '{palette.name}' matches forbidden pattern '{substr}'. "
                    f"Use a perceptually uniform alternative."
                )
        if isinstance(palette, CategoricalPalette):
            self._categorical[palette.name] = palette
        elif isinstance(palette, ContinuousPalette):
            self._continuous[palette.name] = palette
        elif isinstance(palette, DivergingPalette):
            self._diverging[palette.name] = palette

    def load_builtins(self) -> None:
        """Load the built-in approved palettes."""
        # Categorical
        self.register(
            CategoricalPalette(
                name="colorblind_safe_8",
                type="categorical",
                max_categories=8,
                colors=self.COLORBLIND_SAFE_8,
                source="Wong (2011) Nature Methods",
            )
        )
        # Continuous (from matplotlib)
        self.register(ContinuousPalette(name="viridis", type="continuous", source="matplotlib"))
        self.register(ContinuousPalette(name="magma", type="continuous", source="matplotlib"))
        self.register(ContinuousPalette(name="plasma", type="continuous", source="matplotlib"))
        self.register(ContinuousPalette(name="inferno", type="continuous", source="matplotlib"))
        self.register(ContinuousPalette(name="cividis", type="continuous", source="matplotlib"))
        # Scientific Colour Maps (Crameri)
        self.register(
            ContinuousPalette(name="batlow", type="continuous", source="scientific_colour_maps")
        )
        self.register(
            ContinuousPalette(name="devon", type="continuous", source="scientific_colour_maps")
        )
        # Diverging
        self.register(
            DivergingPalette(name="vik", type="diverging", source="scientific_colour_maps")
        )
        self.register(DivergingPalette(name="coolwarm", type="diverging", source="matplotlib"))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PaletteRegistry":
        """Create a PaletteRegistry from a YAML definition file."""
        registry = cls()
        with open(path, "r") as fh:
            data = yaml.safe_load(fh) or {}

        for section_name, section_data in data.items():
            if not isinstance(section_data, dict):
                continue
            if section_name == "qualitative":
                for name, pdata in section_data.items():
                    registry.register(CategoricalPalette(name=name, **pdata))
            elif section_name == "sequential":
                for name, pdata in section_data.items():
                    registry.register(ContinuousPalette(name=name, **pdata))
            elif section_name == "diverging":
                for name, pdata in section_data.items():
                    registry.register(DivergingPalette(name=name, **pdata))
        return registry

    # ── Lookup / 查找 ───────────────────────────────────────────────────

    def get_categorical(self, name: str, n: int = 8) -> list[str]:
        """Get *n* colours from a categorical palette."""
        pal = self._categorical.get(name)
        if pal is None:
            # Fall back to colorblind_safe_8
            pal = self._categorical.get("colorblind_safe_8")
        if pal is None:
            return self.COLORBLIND_SAFE_8[:n]
        if n > pal.max_categories:
            raise ValueError(
                f"Palette '{pal.name}' supports at most {pal.max_categories} "
                f"categories, but {n} were requested. Merge low-abundance categories "
                f"or choose a larger palette."
            )
        return pal.colors[:n]

    def get_continuous(self, name: str) -> str:
        """Get a continuous colormap name (passed to matplotlib)."""
        if name in self._continuous:
            return name
        # Fall back to viridis
        return "viridis"

    def get_diverging(self, name: str) -> str:
        """Get a diverging colormap name."""
        if name in self._diverging:
            return name
        # Fall back to coolwarm
        return "coolwarm"

    def get_matplotlib_colormap(self, name: str, *, diverging_default: bool = False) -> str:
        """Resolve a registered continuous or diverging palette to a cmap name."""
        if name in self._continuous or name in self._diverging:
            return name
        return "coolwarm" if diverging_default else "viridis"

    @property
    def categorical_names(self) -> Set[str]:
        return set(self._categorical.keys())

    @property
    def continuous_names(self) -> Set[str]:
        return set(self._continuous.keys())

    @property
    def diverging_names(self) -> Set[str]:
        return set(self._diverging.keys())

    def is_allowed(self, name: str) -> bool:
        """Check if a palette name is registered (not forbidden)."""
        name_lower = name.lower()
        if name_lower in FORBIDDEN_PALETTES:
            return False
        for substr in FORBIDDEN_SUBSTRINGS:
            if substr in name_lower:
                return False
        return name in self._categorical or name in self._continuous or name in self._diverging

from __future__ import annotations

import hashlib
import math
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class LuoshuPosition(str, Enum):
    S = "S"
    NE = "NE"
    W = "W"
    NW = "NW"
    C = "C"
    SE = "SE"
    E = "E"
    SW = "SW"
    N = "N"


class WuxingChannel(str, Enum):
    WOOD = "W"
    FIRE = "F"
    EARTH = "E"
    METAL = "M"
    WATER = "A"


class CyclePhase(str, Enum):
    ASCENDING = "ascending"
    PEAK = "peak"
    DESCENDING = "descending"
    TROUGH = "trough"


class ChangeType(str, Enum):
    ROOT = "ben"
    SYMPTOM = "biao"
    TRANSFORM = "bian"


LUOSHU_XY = {
    LuoshuPosition.S: (0.0, -1.0),
    LuoshuPosition.NE: (1.0, 1.0),
    LuoshuPosition.W: (-1.0, 0.0),
    LuoshuPosition.NW: (-1.0, 1.0),
    LuoshuPosition.C: (0.0, 0.0),
    LuoshuPosition.SE: (1.0, -1.0),
    LuoshuPosition.E: (1.0, 0.0),
    LuoshuPosition.SW: (-1.0, -1.0),
    LuoshuPosition.N: (0.0, 1.0),
}


CHANNEL_SCALE = {
    WuxingChannel.WOOD: -1.0,
    WuxingChannel.FIRE: -0.5,
    WuxingChannel.EARTH: 0.0,
    WuxingChannel.METAL: 0.5,
    WuxingChannel.WATER: 1.0,
}


CYCLE_SCALE = {
    CyclePhase.ASCENDING: 0.0,
    CyclePhase.PEAK: 1.0 / 3.0,
    CyclePhase.DESCENDING: 2.0 / 3.0,
    CyclePhase.TROUGH: 1.0,
}


class State10D(BaseModel):
    d1_quantity: float = Field(default=1.0, ge=0.0, description="resource magnitude")
    d2_direction: LuoshuPosition = Field(default=LuoshuPosition.C)

    d3_structure_z: int = Field(default=0, ge=-1, le=1)
    d3_energy_w: WuxingChannel = Field(default=WuxingChannel.EARTH)

    d4_change: ChangeType = Field(default=ChangeType.SYMPTOM)
    d4_approaching_threshold: bool = False
    d4_phase_transition: Literal["continuous", "discontinuous", "locked"] = "continuous"

    d5_recovery_rate: float = Field(default=0.5, ge=0.0, le=1.0)
    d5_long_term_cost: float = Field(default=1.0, ge=0.0)
    d5_cycle_phase: CyclePhase = Field(default=CyclePhase.ASCENDING)
    d5_depletion_risk: float = Field(default=0.3, ge=0.0, le=1.0)

    d6_kappa: dict[WuxingChannel, float] = Field(
        default_factory=lambda: {c: 1.0 for c in WuxingChannel}
    )

    d7_role_id: str = ""
    d7_irreversible_commitments: list[str] = Field(default_factory=list)
    d7_exit_cost: float = Field(default=0.0, ge=0.0)

    d8_active: bool = False
    d8_projection_loss: list[str] = Field(default_factory=list)
    d8_return_path: str | None = None
    d8_max_duration: int = Field(default=3, ge=1, le=3)

    d9_equivalence_class: str = ""
    d9_comparable_systems: list[str] = Field(default_factory=list)

    d10_halt_conditions: list[str] = Field(default_factory=list)
    d10_forbidden_claims: list[str] = Field(default_factory=list)
    d10_fallback_dim: int = Field(default=7, ge=1, le=9)

    @field_validator("d6_kappa", mode="before")
    @classmethod
    def _normalize_kappa(cls, value: object) -> dict[WuxingChannel, float]:
        out: dict[WuxingChannel, float] = {channel: 1.0 for channel in WuxingChannel}
        if not isinstance(value, dict):
            return out
        for key, raw in value.items():
            try:
                channel = key if isinstance(key, WuxingChannel) else WuxingChannel(str(key))
                out[channel] = float(raw)
            except Exception:
                continue
        return out

    @model_validator(mode="after")
    def _validate_hard_rules(self) -> "State10D":
        if self.d8_active and not self.d8_return_path:
            raise ValueError("d8_active requires d8_return_path")
        if self.d8_max_duration > 3:
            raise ValueError("d8_max_duration cannot exceed 3")
        return self

    def vector_dim(self, role_embed_dim: int = 8) -> int:
        if role_embed_dim <= 0:
            raise ValueError("role_embed_dim must be positive")
        return 20 + role_embed_dim

    def to_vector(self, role_embedding: list[float] | None = None, role_embed_dim: int = 8) -> list[float]:
        if role_embedding is None:
            role_embedding = _role_embedding(self.d7_role_id, role_embed_dim)
        elif len(role_embedding) != role_embed_dim:
            raise ValueError(f"role_embedding length must be {role_embed_dim}")

        x, y = LUOSHU_XY[self.d2_direction]

        d4_one_hot = [0.0, 0.0, 0.0]
        d4_index = {
            ChangeType.ROOT: 0,
            ChangeType.SYMPTOM: 1,
            ChangeType.TRANSFORM: 2,
        }[self.d4_change]
        d4_one_hot[d4_index] = 1.0

        d5_cost_scaled = math.tanh(self.d5_long_term_cost / 10.0)

        kappa = [self.d6_kappa[channel] for channel in WuxingChannel]
        d8_active = 1.0 if self.d8_active else 0.0
        d9_active = 1.0 if (self.d9_equivalence_class or self.d9_comparable_systems) else 0.0
        d10_halt = 1.0 if self.d10_halt_conditions else 0.0

        return [
            float(self.d1_quantity),
            float(x),
            float(y),
            float(self.d3_structure_z),
            float(CHANNEL_SCALE[self.d3_energy_w]),
            *d4_one_hot,
            float(self.d5_recovery_rate),
            float(d5_cost_scaled),
            float(CYCLE_SCALE[self.d5_cycle_phase]),
            float(self.d5_depletion_risk),
            *[float(v) for v in kappa],
            *[float(v) for v in role_embedding],
            d8_active,
            d9_active,
            d10_halt,
        ]


def _role_embedding(role_id: str, dim: int) -> list[float]:
    seed = hashlib.blake2b(str(role_id).encode("utf-8"), digest_size=32).digest()
    out: list[float] = []
    for i in range(dim):
        b = seed[i % len(seed)]
        out.append((float(b) / 127.5) - 1.0)
    return out


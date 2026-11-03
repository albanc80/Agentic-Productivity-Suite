"""Settings changed in the app, layered over the config files and saved in the local database.

The files (suite.yaml, connectors.yaml, profile.yaml) set the starting defaults. Everything a
person needs to change day to day can be changed in Settings, and "reset" returns to the file.
Two policies stay fixed in the app: restricted data reaches local models only, and connectors
stay read-only.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

TIERS = ("router", "specialist", "synthesis", "review")
OPEN_CLASSES = ("public", "internal", "confidential")  # "restricted" is always local-only


class BudgetsEdit(BaseModel):
    max_run_cost_usd: float = Field(ge=0, le=10_000)
    max_run_tokens: int = Field(ge=1_000, le=100_000_000)
    max_steps: int = Field(ge=1, le=500)
    max_tool_calls_per_step: int = Field(ge=0, le=100)
    max_tool_result_chars: int = Field(ge=1_000, le=1_000_000)
    max_context_fraction: float = Field(ge=0.2, le=0.95)


class TierPref(BaseModel):
    order: list[str] = Field(default_factory=list)  # chosen order of model refs
    excluded: list[str] = Field(default_factory=list)  # refs the person removed from the chain


class GeneralSettings(BaseModel):
    budgets: BudgetsEdit | None = None
    persona_chat: bool | None = None
    persona_exports: bool | None = None
    store_prompts: bool | None = None
    default_data_class: Literal["public", "internal", "confidential", "restricted"] | None = None
    cloud_allowed: dict[Literal["public", "internal", "confidential"], bool] | None = None
    tiers: dict[Literal["router", "specialist", "synthesis", "review"], TierPref] | None = None
    agent_models: dict[str, str] | None = None  # online: agent id -> model ref tried first
    offline_model: str | None = None  # offline: the local model every agent uses first


class GeneralEdit(BaseModel):
    """PUT body: only the fields sent are changed."""

    budgets: BudgetsEdit | None = None
    persona_chat: bool | None = None
    persona_exports: bool | None = None
    store_prompts: bool | None = None
    default_data_class: Literal["public", "internal", "confidential", "restricted"] | None = None
    cloud_allowed: dict[Literal["public", "internal", "confidential"], bool] | None = None
    tiers: dict[Literal["router", "specialist", "synthesis", "review"], list[str]] | None = None  # desired order
    agent_models: dict[str, str | None] | None = None  # null or "" = back to automatic
    offline_model: str | None = None  # "" = automatic (first available local model)


def _clean_lines(v: list[str]) -> list[str]:
    return [x.strip()[:500] for x in v if x and x.strip()][:20]


class ProfileEdit(BaseModel):
    name: str = Field(default="", max_length=200)
    role: str = Field(default="", max_length=300)
    organization_context: str = Field(default="", max_length=2000)
    goals: list[str] = Field(default_factory=list)
    working_preferences: list[str] = Field(default_factory=list)
    domain_notes: str = Field(default="", max_length=4000)

    @field_validator("goals", "working_preferences")
    @classmethod
    def _lines(cls, v: list[str]) -> list[str]:
        return _clean_lines(v)


class ConnectorEdit(BaseModel):
    enabled: bool | None = None
    values: dict[str, str] | None = None  # variable -> value; "" keeps a saved secret and clears a plain value
    clear: list[str] = Field(default_factory=list)  # variables to forget
    folders: list[str] | None = None  # local files

    @field_validator("values")
    @classmethod
    def _values(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return v
        for k, val in v.items():
            if "\n" in val or "\r" in val or len(val) > 4000:
                raise ValueError(f"{k}: one line, at most 4000 characters")
        return {k: val.strip() for k, val in v.items()}


def order_chain(computed: list[str], pref: TierPref) -> list[str]:
    """The person's order first (refs that still exist), then any new refs, minus the ones they removed."""
    out = [r for r in pref.order if r in computed]
    out += [r for r in computed if r not in out and r not in pref.excluded]
    return out

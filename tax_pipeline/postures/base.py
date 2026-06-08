from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputSurfaceSupport:
    ordinary_law: bool
    forms: bool
    entry_sheet: bool


@dataclass(frozen=True)
class PostureDefinition:
    jurisdiction: str
    filing_posture: str
    module_path: str
    required_household_shape: str
    output_support: OutputSurfaceSupport
    legal_rule_keys: tuple[str, ...] = ()
    implemented: bool = True


def validate_household_shape(required_household_shape: str, person_count: int) -> None:
    if required_household_shape == "single" and person_count != 1:
        raise ValueError("Single filing posture requires exactly 1 person.")
    if required_household_shape == "married" and person_count != 2:
        raise ValueError("Married filing posture requires exactly 2 people.")

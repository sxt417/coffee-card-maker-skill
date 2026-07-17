#!/usr/bin/env python3
"""Resolve ordered coffee flavor words to deterministic colors and weights."""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[，,、/|·•]+", " ", text)
    return re.sub(r"[\s\-_'\u2019\u2018\u201c\u201d()（）]+", "", text)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#%02X%02X%02X" % tuple(
        max(0, min(255, round(channel))) for channel in rgb
    )


def mix_hex(base: str, overlay: str, amount: float) -> str:
    a = hex_to_rgb(base)
    b = hex_to_rgb(overlay)
    return rgb_to_hex(tuple(a[i] * (1 - amount) + b[i] * amount for i in range(3)))


def apply_modifier(color: str, rule: dict[str, Any]) -> str:
    r, g, b = (channel / 255 for channel in hex_to_rgb(color))
    h, lightness, saturation = colorsys.rgb_to_hls(r, g, b)

    h = (h + rule.get("hueShiftDegrees", 0) / 360) % 1
    lightness = max(0, min(1, lightness + rule.get("lightnessDelta", 0)))
    saturation = max(0, min(1, saturation + rule.get("saturationDelta", 0)))

    r, g, b = colorsys.hls_to_rgb(h, lightness, saturation)
    adjusted = rgb_to_hex((r * 255, g * 255, b * 255))

    if rule.get("mixWith"):
        adjusted = mix_hex(adjusted, rule["mixWith"], rule.get("mixAmount", 0))
    return adjusted


def stable_family_fallback(word: str, fallback: dict[str, str]) -> str:
    """Make a small deterministic variation around the fixed family color."""
    base = fallback["primary"]
    digest = hashlib.sha256(normalize(word).encode("utf-8")).digest()
    hue_delta = ((digest[0] / 255) - 0.5) * 10
    light_delta = ((digest[1] / 255) - 0.5) * 0.08
    sat_delta = ((digest[2] / 255) - 0.5) * 0.08
    return apply_modifier(base, {
        "hueShiftDegrees": hue_delta,
        "lightnessDelta": light_delta,
        "saturationDelta": sat_delta,
    })


def build_indexes(data: dict[str, Any]):
    by_id = {item["id"]: item for item in data["flavors"]}
    alias_to_id: dict[str, str] = {}
    for item in data["flavors"]:
        for token in [item["nameZh"], item["nameEn"], *item["aliases"]]:
            alias_to_id[normalize(token)] = item["id"]
    longest_aliases = sorted(alias_to_id, key=len, reverse=True)
    return by_id, alias_to_id, longest_aliases


def resolve_one(
    raw: str,
    data: dict[str, Any],
    by_id: dict[str, Any],
    alias_to_id: dict[str, str],
    longest_aliases: list[str],
    fallback_family: str | None = None,
) -> dict[str, Any]:
    normalized = normalize(raw)
    item = None
    match_type = None
    matched_alias = None

    if normalized in alias_to_id:
        item = by_id[alias_to_id[normalized]]
        match_type = "exact"
        matched_alias = normalized
    else:
        for alias in longest_aliases:
            if len(alias) >= 2 and alias in normalized:
                item = by_id[alias_to_id[alias]]
                match_type = "contained-alias"
                matched_alias = alias
                break

    modifier_ids = []
    if item:
        primary = item["primary"]
        for rule in data.get("modifierRules", []):
            if any(normalize(token) in normalized for token in rule["tokens"]):
                # Do not double-apply a modifier already encoded in a canonical term.
                if not any(normalize(token) == matched_alias for token in rule["tokens"]):
                    primary = apply_modifier(primary, rule)
                    modifier_ids.append(rule["id"])

        return {
            "input": raw,
            "normalized": normalized,
            "canonical": item["nameZh"],
            "english": item["nameEn"],
            "family": item["categoryId"],
            "primary": primary,
            "basePrimary": item["primary"],
            "light": item["light"],
            "dark": item["dark"],
            "textColor": item["textColor"],
            "source": "dictionary",
            "matchType": match_type,
            "modifiers": modifier_ids,
        }

    family = fallback_family if fallback_family in data["familyFallbacks"] else None
    if not family:
        return {
            "input": raw,
            "normalized": normalized,
            "source": "unresolved",
            "error": "Unknown flavor. Supply an aligned --families value inferred by Codex.",
        }

    fallback = data["familyFallbacks"][family]
    primary = stable_family_fallback(raw, fallback)
    return {
        "input": raw,
        "normalized": normalized,
        "canonical": raw.strip(),
        "family": family,
        "primary": primary,
        "basePrimary": fallback["primary"],
        "light": fallback["light"],
        "dark": fallback["dark"],
        "textColor": "#111111",
        "source": "deterministic-family-fallback",
        "matchType": "family-fallback",
        "modifiers": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flavors", required=True, help="Comma-separated ordered flavor words")
    parser.add_argument(
        "--palette",
        default=str(Path(__file__).resolve().parents[1] / "references" / "flavor-colors.json"),
    )
    parser.add_argument(
        "--families",
        default="",
        help="Optional comma-separated fallback family IDs aligned with flavors",
    )
    parser.add_argument("--decay", type=float, default=0.82)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    with open(args.palette, "r", encoding="utf-8") as f:
        data = json.load(f)

    flavors = [part.strip() for part in re.split(r"[,，、/|]", args.flavors) if part.strip()]
    families = [part.strip() for part in args.families.split(",")] if args.families else []
    by_id, alias_to_id, longest_aliases = build_indexes(data)

    raw_weights = [args.decay ** index for index in range(len(flavors))]
    weight_total = sum(raw_weights) or 1

    resolved = []
    for index, flavor in enumerate(flavors):
        fallback_family = families[index] if index < len(families) else None
        item = resolve_one(
            flavor, data, by_id, alias_to_id, longest_aliases, fallback_family
        )
        item["weight"] = round(raw_weights[index] / weight_total, 6)
        resolved.append(item)

    output = {
        "paletteVersion": data["paletteVersion"],
        "weightDecay": args.decay,
        "flavors": resolved,
    }

    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()

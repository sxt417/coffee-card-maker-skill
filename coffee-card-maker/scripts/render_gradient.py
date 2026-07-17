#!/usr/bin/env python3
"""渲染带中文或英文名称与风味文字的有机咖啡风味渐变卡。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import secrets
import sys
from pathlib import Path
from typing import Any

from resolve_flavor_colors import build_indexes, resolve_one

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "缺少运行依赖，请执行：python3 -m pip install numpy pillow"
    ) from exc

SKILL_ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = SKILL_ROOT / "references" / "flavor-colors.json"
FONT_DIR = Path.home() / "Library" / "Fonts"
SYSTEM_FONTS = {
    ("en", "coffee"): FONT_DIR / "PPEditorialNew-Regular.otf",
    ("en", "flavor"): FONT_DIR / "SuisseIntlTrial-Medium.otf",
}

FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "floral": ("花", "玫瑰", "茉莉", "桂", "紫罗兰", "薰衣草", "floral", "flower"),
    "citrus": ("柠", "橙", "橘", "柑", "柚", "佛手柑", "lime", "lemon", "citrus"),
    "berry": ("莓", "醋栗", "加仑", "berry", "currant"),
    "orchard_stone": ("桃", "杏", "李", "梅", "樱桃", "苹果", "梨", "葡萄", "石榴", "peach", "plum", "apricot", "cherry", "apple", "pear", "grape"),
    "tropical_melon": ("瓜", "芒果", "菠萝", "凤梨", "百香果", "香蕉", "木瓜", "番石榴", "芭乐", "荔枝", "椰", "melon", "watermelon", "tropical"),
    "dried_fruit": ("果干", "葡萄干", "枣", "无花果", "dried", "raisin", "date", "fig"),
    "sweet_bakery": ("蜜", "糖", "焦糖", "香草", "奶油", "太妃", "饼干", "面包", "honey", "sugar", "caramel", "vanilla", "biscuit"),
    "nuts_cocoa": ("巧克力", "可可", "坚果", "杏仁", "榛子", "核桃", "花生", "chocolate", "cocoa", "nut"),
    "tea_herbal": ("茶", "草", "薄荷", "香茅", "迷迭香", "tea", "oolong", "herbal", "mint", "grass"),
    "spice": ("肉桂", "丁香", "胡椒", "姜", "香料", "spice", "cinnamon", "clove", "pepper"),
    "boozy_fermented": ("酒", "发酵", "乳酸", "酸奶", "wine", "rum", "brandy", "whisk", "ferment", "yogurt", "lactic"),
    "roasted_woody": ("烟", "烘", "木", "roast", "smok", "wood"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flavors", required=True, help="用逗号、斜杠、分号或中文顿号分隔的风味词")
    parser.add_argument("--language", choices=("en", "zh"), default="en", help="卡片文字版本：en 英文，zh 中文")
    parser.add_argument("--coffee-name", required=True, help="用于卡片展示的咖啡名称；语言须与 --language 一致")
    parser.add_argument("--display-flavors", required=True, help="用于卡片展示的风味词；语言须与 --language 一致")
    parser.add_argument("--coffee-font", help="可选；指定标题字体文件，仍会严格校验字体身份")
    parser.add_argument("--flavor-font", help="可选；指定风味字体文件，仍会严格校验字体身份")
    parser.add_argument("--colors", help="可选；与风味顺序对应、以逗号分隔的 HEX 自定义颜色")
    parser.add_argument("--output", default="coffee-card.png", help="PNG 输出路径")
    parser.add_argument("--seed", type=int, help="构图种子；省略时随机生成")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1440)
    parser.add_argument("--grain", type=float, default=0.024)
    parser.add_argument("--decay", type=float, default=0.82)
    parser.add_argument(
        "--optimize-png",
        action="store_true",
        help="可选；用更慢的 PNG 压缩换取略小文件，默认优先生成速度",
    )
    return parser.parse_args()


def normalized_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", value.lower())


def font_matches(path: Path, family: str, weight: str, language: str, role: str) -> bool:
    if language == "en":
        expected = ("PP Editorial New", "Regular") if role == "coffee" else ("Suisse Intl Trial", "Medium")
        return (family, weight) == expected

    family_key = normalized_identity(family)
    filename_key = normalized_identity(path.stem)
    if role == "coffee":
        return (
            "造字工房悦黑" in family_key
            or "zaozigongfangyuehei" in family_key
            or "zzgfyh" in family_key
            or "mfyuehei" in family_key
        )

    is_lanting = any(marker in family_key for marker in ("方正兰亭", "fzlantinghei", "lantinghei"))
    is_medium = (
        "medium" in normalized_identity(weight)
        or "medium" in family_key
        or bool(re.search(r"(?:^|[-_])m(?:[-_]|$)", path.stem, flags=re.IGNORECASE))
        or "fzltm" in filename_key
        or "fzlantingheisdbgb" in family_key
        or filename_key == "fzltzhjw"
    )
    return is_lanting and is_medium


def expected_font_label(language: str, role: str) -> str:
    if language == "en":
        return "PP Editorial New Regular" if role == "coffee" else "Suisse Intl Trial Medium"
    return "造字工房悦黑" if role == "coffee" else "方正兰亭 Medium（中黑 / DB）"


def resolve_required_font(language: str, role: str, override: str | None) -> Path:
    if override:
        candidates = [Path(override).expanduser()]
    else:
        candidates = []
        system_font = SYSTEM_FONTS.get((language, role))
        if system_font:
            candidates.append(system_font)
        if FONT_DIR.is_dir():
            candidates.extend(
                sorted(
                    path
                    for path in FONT_DIR.iterdir()
                    if path.is_file() and path.suffix.lower() in {".otf", ".ttf", ".ttc"}
                )
            )

    for path in candidates:
        if not path.is_file():
            continue
        try:
            probe = ImageFont.truetype(str(path), size=40)
        except OSError:
            continue
        family, weight = probe.getname()
        if font_matches(path, family, weight, language, role):
            return path
    option = "--coffee-font" if role == "coffee" else "--flavor-font"
    raise FileNotFoundError(
        f"找不到或无法验证指定字体：{expected_font_label(language, role)}。"
        f"请将合法取得的字体安装到 {FONT_DIR}，或用 {option} 指定字体文件；"
        f"禁止使用替代字体，且不要将受限字体上传到公开仓库。"
    )


def load_required_font(path: Path, size: int, language: str, role: str) -> ImageFont.FreeTypeFont:
    """Load and verify the exact required font; never substitute a fallback."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Required font file is missing: {path} ({expected_font_label(language, role)})"
        )
    try:
        font = ImageFont.truetype(str(path), size=size)
    except OSError as exc:
        raise RuntimeError(
            f"Required font failed to load: {path} ({expected_font_label(language, role)})"
        ) from exc

    actual_family, actual_weight = font.getname()
    if not font_matches(path, actual_family, actual_weight, language, role):
        raise RuntimeError(
            "Required font identity mismatch: "
            f"expected {expected_font_label(language, role)}, "
            f"got {actual_family} {actual_weight} from {path}"
        )
    return font


def tracked_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, spacing: float) -> float:
    if not text:
        return 0.0
    # Shape each text segment as a whole so native kerning is kept. The trial
    # Suisse font has no pipe glyph, so separators use a fixed geometric width.
    parts = text.split("|")
    pipe_width = font.size * 0.22
    return (
        sum(draw.textlength(part, font=font) for part in parts)
        + pipe_width * (len(parts) - 1)
        + spacing * max(0, len(text) - 1)
    )


def draw_tracked_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: float,
    y: float,
    font: ImageFont.FreeTypeFont,
    spacing: float,
) -> None:
    x = center_x - tracked_width(draw, text, font, spacing) / 2
    parts = text.split("|")
    pipe_width = font.size * 0.22
    # ``y`` is the visual line top. Draw every glyph on one shared baseline;
    # using the old ``lt`` anchor aligned glyph bounding-box tops and made
    # capitals, lowercase letters and descenders visibly jump vertically.
    ascent, _ = font.getmetrics()
    baseline_y = y + ascent
    for part_index, part in enumerate(parts):
        for char_index, char in enumerate(part):
            glyph_x = x + draw.textlength(part[:char_index], font=font) + spacing * char_index
            draw.text((glyph_x, baseline_y), char, font=font, fill="#FFFFFF", anchor="ls")
        x += draw.textlength(part, font=font) + spacing * len(part)
        if part_index < len(parts) - 1:
            pipe_x = x + pipe_width / 2
            draw.line(
                (pipe_x, y + font.size * 0.26, pipe_x, y + font.size * 0.88),
                fill="#FFFFFF",
                width=max(1, round(font.size * 0.035)),
            )
            x += pipe_width + spacing


def wrap_words(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    spacing: float,
    max_width: float,
) -> list[str] | None:
    lines: list[str] = []
    for paragraph in (part.strip() for part in text.splitlines()):
        if not paragraph:
            continue
        current = ""
        for word in paragraph.split():
            candidate = word if not current else f"{current} {word}"
            if tracked_width(draw, candidate, font, spacing) <= max_width:
                current = candidate
            elif current and tracked_width(draw, word, font, spacing) <= max_width:
                lines.append(current)
                current = word
            else:
                return None
        if current:
            lines.append(current)
    return lines or None


def normalize_mixed_cjk_spacing(text: str) -> str:
    """Keep mixed Chinese, Latin text, and numbers visually separated."""
    text = re.sub(r"[ \t]+", " ", text.strip())
    text = re.sub(r"(?<=[\u3400-\u9fff])(?=[A-Za-z0-9])", " ", text)
    text = re.sub(r"(?<=[A-Za-z0-9])(?=[\u3400-\u9fff])", " ", text)
    return text


def wrap_cjk(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    spacing: float,
    max_width: float,
) -> list[str] | None:
    lines: list[str] = []
    for paragraph in (part.strip() for part in text.splitlines()):
        if not paragraph:
            continue
        paragraph = normalize_mixed_cjk_spacing(paragraph)
        tokens = re.findall(r"[\u3400-\u9fff]|[^\s\u3400-\u9fff]+|\s+", paragraph)
        current = ""
        pending_space = False
        for token in tokens:
            if token.isspace():
                pending_space = bool(current)
                continue
            separator = " " if pending_space and current else ""
            candidate = current + separator + token
            if tracked_width(draw, candidate, font, spacing) <= max_width:
                current = candidate
            elif current and tracked_width(draw, token, font, spacing) <= max_width:
                lines.append(current)
                current = token
            else:
                return None
            pending_space = False
        if current:
            lines.append(current)
    return lines or None


def fit_coffee_name(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, scale: float,
    language: str, font_path: Path,
) -> tuple[ImageFont.FreeTypeFont, list[str], float, float]:
    for size in range(round(72 * scale), round(52 * scale) - 1, -max(1, round(2 * scale))):
        font = load_required_font(font_path, size, language, "coffee")
        spacing = -0.02 * size
        lines = (wrap_cjk if language == "zh" else wrap_words)(draw, text, font, spacing, max_width)
        if lines and len(lines) <= 6:
            return font, lines, spacing, size * 1.15
    raise ValueError("咖啡名称在最小字号下仍无法放入 6 行安全区域")


def fit_flavor_lines(
    draw: ImageDraw.ImageDraw, flavors: list[str], max_width: int, scale: float,
    language: str, font_path: Path,
) -> tuple[ImageFont.FreeTypeFont, list[str], float, float]:
    for size in range(round(38 * scale), round(28 * scale) - 1, -max(1, round(scale))):
        font = load_required_font(font_path, size, language, "flavor")
        spacing = -0.01 * size
        one_line = " | ".join(flavors)
        if tracked_width(draw, one_line, font, spacing) <= max_width:
            return font, [one_line], spacing, size * 1.35

        candidates: list[tuple[float, list[str]]] = []
        for split_at in range(1, len(flavors)):
            lines = [" | ".join(flavors[:split_at]), " | ".join(flavors[split_at:])]
            widths = [tracked_width(draw, line, font, spacing) for line in lines]
            if max(widths) <= max_width:
                candidates.append((abs(widths[0] - widths[1]), lines))
        if candidates:
            return font, min(candidates, key=lambda item: item[0])[1], spacing, size * 1.35
    raise ValueError("风味文字在最小字号下仍无法放入两行安全区域；不得裁切、拆词或生成第三行")


def add_typography(
    image: Image.Image,
    coffee_name: str,
    display_flavors: list[str],
    language: str,
    coffee_font_path: Path,
    flavor_font_path: Path,
) -> dict[str, Any]:
    width, height = image.size
    scale = width / 1080
    side_padding = round(100 * scale)
    bottom_padding = round(100 * scale)
    max_width = width - side_padding * 2
    draw = ImageDraw.Draw(image)

    title_font, title_lines, title_spacing, title_line_height = fit_coffee_name(
        draw, coffee_name.strip(), max_width, scale, language, coffee_font_path
    )
    title_y = height * 0.45 - title_line_height * len(title_lines) / 2
    for index, line in enumerate(title_lines):
        draw_tracked_centered(draw, line, width / 2, title_y + index * title_line_height, title_font, title_spacing)

    flavor_font, flavor_lines, flavor_spacing, flavor_line_height = fit_flavor_lines(
        draw, display_flavors, max_width, scale, language, flavor_font_path
    )
    flavor_y = height - bottom_padding - flavor_line_height * len(flavor_lines)
    for index, line in enumerate(flavor_lines):
        draw_tracked_centered(draw, line, width / 2, flavor_y + index * flavor_line_height, flavor_font, flavor_spacing)

    return {
        "coffee_name": {
            "text": coffee_name.strip(),
            "font_family": title_font.getname()[0],
            "font_weight": title_font.getname()[1],
            "font_file": str(coffee_font_path),
            "font_size": title_font.size, "lines": title_lines, "center_y_ratio": 0.45,
        },
        "display_flavors": {
            "items": display_flavors,
            "font_family": flavor_font.getname()[0],
            "font_weight": flavor_font.getname()[1],
            "font_file": str(flavor_font_path),
            "font_size": flavor_font.size, "lines": flavor_lines, "bottom_padding": bottom_padding,
        },
        "language": language,
        "safe_area": {"left": side_padding, "right": side_padding},
    }


def stable_int(text: str, bytes_count: int = 8) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:bytes_count], "big")


def split_flavors(raw: str) -> list[str]:
    normalized = raw
    for sep in ("，", "、", "/", "；", ";", "|", "\n", "＋", "+"):
        normalized = normalized.replace(sep, ",")
    items = [item.strip() for item in normalized.split(",") if item.strip()]
    if not 2 <= len(items) <= 8:
        raise ValueError(f"需要输入 2–8 个风味词，当前收到 {len(items)} 个")
    return items


def normalize_word(word: str) -> str:
    return " ".join(word.strip().lower().split())


def load_palette() -> dict[str, Any]:
    with PALETTE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def infer_family(word: str) -> str:
    norm = normalize_word(word)
    for family, keywords in FAMILY_KEYWORDS.items():
        if any(keyword.lower() in norm for keyword in keywords):
            return family
    families = tuple(FAMILY_KEYWORDS)
    return families[stable_int(norm) % len(families)]


def resolve_palette(flavors: list[str], data: dict[str, Any], overrides: list[str] | None) -> list[dict[str, Any]]:
    if overrides and len(overrides) != len(flavors):
        raise ValueError("自定义颜色数量必须与风味词数量一致")

    by_id, alias_to_id, longest_aliases = build_indexes(data)
    resolved: list[dict[str, Any]] = []

    for i, original in enumerate(flavors):
        norm = normalize_word(original)
        if overrides:
            hex_value = normalize_hex(overrides[i])
            resolved.append({
                "input": original,
                "normalized": norm,
                "canonical": original,
                "hex": hex_value,
                "family": "override",
                "source": "override",
            })
            continue

        family = infer_family(norm)
        item = resolve_one(
            original,
            data,
            by_id,
            alias_to_id,
            longest_aliases,
            fallback_family=family,
        )
        item["hex"] = normalize_hex(item["primary"])
        resolved.append(item)

    return resolved


def normalize_hex(value: str) -> str:
    value = value.strip().upper()
    if not value.startswith("#"):
        value = "#" + value
    if len(value) == 4:
        value = "#" + "".join(ch * 2 for ch in value[1:])
    if len(value) != 7 or any(ch not in "0123456789ABCDEF" for ch in value[1:]):
        raise ValueError(f"无效的 HEX 颜色：{value}")
    return value


def compute_weights(count: int, decay: float) -> np.ndarray:
    if not 0.5 < decay < 1.0:
        raise ValueError("衰减系数必须介于 0.5 和 1.0 之间")
    raw = np.array([decay**i for i in range(count)], dtype=np.float32)
    return raw / raw.sum()


def hex_to_srgb(hex_value: str) -> np.ndarray:
    return np.array([int(hex_value[i : i + 2], 16) / 255.0 for i in (1, 3, 5)], dtype=np.float32)


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - 0.055)


def linear_srgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    r, g, b = np.moveaxis(rgb, -1, 0)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = np.cbrt(np.maximum(l, 0)), np.cbrt(np.maximum(m, 0)), np.cbrt(np.maximum(s, 0))
    return np.stack(
        [
            0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
        ],
        axis=-1,
    )


def oklab_to_linear_srgb(lab: np.ndarray) -> np.ndarray:
    L, a, b = np.moveaxis(lab, -1, 0)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    return np.stack(
        [
            4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
        ],
        axis=-1,
    )


def smooth_noise(rng: np.random.Generator, width: int, height: int, grid_x: int, grid_y: int, blur: float = 0.0) -> np.ndarray:
    small = rng.normal(0.0, 1.0, (grid_y, grid_x)).astype(np.float32)
    low = float(small.min())
    high = float(small.max())
    normalized = (small - low) / max(high - low, 1e-6)
    image = Image.fromarray(np.uint8(np.clip(normalized, 0, 1) * 255), mode="L")
    image = image.resize((width, height), Image.Resampling.BICUBIC)
    if blur > 0:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    arr = np.asarray(image, dtype=np.float32) / 255.0
    arr = (arr - arr.mean()) / max(arr.std(), 1e-6)
    return arr


def make_warp(rng: np.random.Generator, width: int, height: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coarse = smooth_noise(rng, width, height, 5, 7, blur=width * 0.012)
    medium = smooth_noise(rng, width, height, 9, 12, blur=width * 0.007)
    potential = 0.72 * coarse + 0.28 * medium
    gy, gx = np.gradient(potential)
    norm = np.sqrt(gx * gx + gy * gy)
    scale = np.percentile(norm, 95)
    if scale > 0:
        gx /= scale
        gy /= scale
    curl_x = gy
    curl_y = -gx
    luminance_noise = smooth_noise(rng, width, height, 7, 10, blur=width * 0.01)
    return curl_x, curl_y, luminance_noise


def elliptical_field(
    X: np.ndarray,
    Y: np.ndarray,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    angle: float,
    falloff: float,
) -> np.ndarray:
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    dx = X - cx
    dy = Y - cy
    u = (dx * cos_a + dy * sin_a) / max(rx, 1e-3)
    v = (-dx * sin_a + dy * cos_a) / max(ry, 1e-3)
    d2 = u * u + v * v
    return np.exp(-np.power(np.maximum(d2, 0), falloff / 2.0) * 1.55)


def render(
    palette: list[dict[str, Any]],
    weights: np.ndarray,
    width: int,
    height: int,
    composition_seed: int,
    grain_strength: float,
) -> Image.Image:
    if width * 4 != height * 3:
        raise ValueError("输出尺寸必须严格保持 3:4 比例")
    if width < 300 or height < 400:
        raise ValueError("输出尺寸过小，至少使用 300 × 400")

    work_width = max(360, width // 2)
    work_height = max(480, height // 2)
    rng = np.random.default_rng(composition_seed)

    x = np.linspace(0.0, 1.0, work_width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, work_height, dtype=np.float32)
    X, Y = np.meshgrid(x, y)

    curl_x, curl_y, luminance_noise = make_warp(rng, work_width, work_height)
    warp_amount = rng.uniform(0.035, 0.085)
    Xw = X + curl_x * warp_amount
    Yw = Y + curl_y * warp_amount * 0.82

    fields: list[np.ndarray] = []
    max_weight = float(weights.max())

    for index, weight in enumerate(weights):
        relative = float(weight / max_weight)
        blob_count = 1 + int(index < 2) + int(rng.random() < (0.28 + 0.28 * relative))
        influence = np.zeros((work_height, work_width), dtype=np.float32)

        for blob_index in range(blob_count):
            edge_bias = rng.random() < 0.48
            if edge_bias:
                side = int(rng.integers(0, 4))
                if side == 0:
                    cx, cy = rng.uniform(-0.28, 0.12), rng.uniform(-0.08, 1.08)
                elif side == 1:
                    cx, cy = rng.uniform(0.88, 1.28), rng.uniform(-0.08, 1.08)
                elif side == 2:
                    cx, cy = rng.uniform(-0.08, 1.08), rng.uniform(-0.25, 0.12)
                else:
                    cx, cy = rng.uniform(-0.08, 1.08), rng.uniform(0.88, 1.25)
            else:
                cx, cy = rng.uniform(0.02, 0.98), rng.uniform(0.02, 0.98)

            area_scale = 0.70 + 0.55 * relative
            rx = rng.uniform(0.32, 0.72) * area_scale
            ry = rng.uniform(0.22, 0.58) * area_scale
            angle = rng.uniform(-math.pi, math.pi)
            falloff = rng.uniform(1.45, 2.45)
            strength = rng.uniform(0.65, 1.15) * (1.0 if blob_index == 0 else 0.58)
            influence += elliptical_field(Xw, Yw, cx, cy, rx, ry, angle, falloff) * strength

        # 归一化每个风味色域，确保所有请求的风味都有可见区域。
        influence /= max(float(influence.max()), 1e-6)
        influence = np.power(0.018 + influence, rng.uniform(1.05, 1.42))
        # 顺序控制覆盖范围和重复程度，但靠后的风味不能消失。
        influence *= 0.58 + 0.92 * relative
        fields.append(influence)

    stack = np.stack(fields, axis=0)
    # 使用柔和的区域胜出模型：颜色保持扩散，但不会平均成米色或灰色。
    order_bias = np.power(weights / weights.max(), 0.52).astype(np.float32)
    regional_contrast = rng.uniform(1.65, 2.25)
    # 校准全局色域偏置，使平均视觉覆盖率符合请求的顺序权重。
    calibrated_bias = order_bias.copy()
    for _ in range(10):
        adjusted = np.maximum(stack * calibrated_bias[:, None, None], 1e-8)
        powered = np.power(adjusted, regional_contrast)
        provisional = powered / np.maximum(powered.sum(axis=0, keepdims=True), 1e-8)
        observed = provisional.mean(axis=(1, 2))
        calibrated_bias *= np.power(weights / np.maximum(observed, 1e-6), 0.72)
        calibrated_bias /= max(float(calibrated_bias.max()), 1e-6)
    adjusted = np.maximum(stack * calibrated_bias[:, None, None], 1e-8)
    powered = np.power(adjusted, regional_contrast)
    mix_weights = powered / np.maximum(powered.sum(axis=0, keepdims=True), 1e-8)

    srgb_colors = np.stack([hex_to_srgb(item["hex"]) for item in palette], axis=0)
    oklab_colors = linear_srgb_to_oklab(srgb_to_linear(srgb_colors))
    canvas_lab = np.einsum("nhw,nc->hwc", mix_weights, oklab_colors, optimize=True)

    # 添加一个宽阔、明亮且可呼吸的区域。
    light_field = elliptical_field(
        Xw,
        Yw,
        rng.uniform(-0.10, 1.10),
        rng.uniform(-0.08, 0.90),
        rng.uniform(0.34, 0.68),
        rng.uniform(0.28, 0.62),
        rng.uniform(-math.pi, math.pi),
        rng.uniform(1.5, 2.2),
    )
    light_alpha = rng.uniform(0.08, 0.22) * light_field[..., None]
    warm_light = np.array([0.945, rng.uniform(-0.005, 0.018), rng.uniform(-0.005, 0.025)], dtype=np.float32)
    canvas_lab = canvas_lab * (1.0 - light_alpha) + warm_light * light_alpha

    # 添加较深的锚点区域，同时保持原有色相家族。
    darkest_index = int(np.argmin(oklab_colors[:, 0] - weights * 0.08))
    anchor_field = elliptical_field(
        Xw,
        Yw,
        rng.choice([-0.10, 1.10, rng.uniform(0.15, 0.85)]),
        rng.choice([-0.08, 1.08, rng.uniform(0.55, 0.95)]),
        rng.uniform(0.28, 0.58),
        rng.uniform(0.22, 0.52),
        rng.uniform(-math.pi, math.pi),
        rng.uniform(1.6, 2.4),
    )
    anchor_color = oklab_colors[darkest_index].copy()
    anchor_color[0] = max(0.22, anchor_color[0] - rng.uniform(0.05, 0.14))
    anchor_alpha = rng.uniform(0.05, 0.17) * anchor_field[..., None]
    canvas_lab = canvas_lab * (1.0 - anchor_alpha) + anchor_color * anchor_alpha

    # 使用低频明度调制增强氛围纵深。
    canvas_lab[..., 0] += np.clip(luminance_noise, -2.0, 2.0) * rng.uniform(0.004, 0.014)

    linear_rgb = oklab_to_linear_srgb(canvas_lab)
    srgb = np.clip(linear_to_srgb(linear_rgb), 0.0, 1.0)
    image = Image.fromarray(np.uint8(srgb * 255.0), mode="RGB")
    image = image.resize((width, height), Image.Resampling.LANCZOS)

    # 在最终分辨率下添加细腻的哑光颗粒。
    full = np.asarray(image, dtype=np.float32) / 255.0
    grain_rng = np.random.default_rng(composition_seed ^ 0xA5A5A5A5)
    mono = grain_rng.normal(0.0, 1.0, (height, width, 1)).astype(np.float32)
    colored = grain_rng.normal(0.0, 1.0, (height, width, 3)).astype(np.float32)
    texture = mono * grain_strength * 0.70 + colored * grain_strength * 0.16
    # 中间调颗粒稍强，高光和深阴影区域更安静。
    luma = full.mean(axis=2, keepdims=True)
    midtone_mask = 0.60 + 0.40 * (1.0 - np.abs(luma - 0.5) * 1.5)
    full = np.clip(full + texture * midtone_mask, 0.0, 1.0)
    return Image.fromarray(np.uint8(full * 255.0), mode="RGB")


def main() -> int:
    args = parse_args()
    try:
        flavors = split_flavors(args.flavors)
        display_flavors = split_flavors(args.display_flavors)
        if len(display_flavors) != len(flavors):
            raise ValueError("--display-flavors 必须与 --flavors 数量一致并保持相同顺序")
        if not args.coffee_name.strip():
            raise ValueError("--coffee-name 不能为空")
        overrides = None
        if args.colors:
            overrides = [normalize_hex(item) for item in args.colors.replace("，", ",").split(",") if item.strip()]
        data = load_palette()
        palette = resolve_palette(flavors, data, overrides)
        weights = compute_weights(len(flavors), args.decay)
        composition_seed = args.seed if args.seed is not None else secrets.randbits(32)
        coffee_font_path = resolve_required_font(args.language, "coffee", args.coffee_font)
        flavor_font_path = resolve_required_font(args.language, "flavor", args.flavor_font)

        output = Path(args.output).expanduser().resolve()
        if output.suffix.lower() != ".png":
            output = output.with_suffix(".png")
        output.parent.mkdir(parents=True, exist_ok=True)

        image = render(
            palette=palette,
            weights=weights,
            width=args.width,
            height=args.height,
            composition_seed=composition_seed,
            grain_strength=float(np.clip(args.grain, 0.0, 0.08)),
        )
        typography = add_typography(
            image,
            args.coffee_name,
            display_flavors,
            args.language,
            coffee_font_path,
            flavor_font_path,
        )
        image.save(output, format="PNG", optimize=args.optimize_png)

        palette_key_text = "|".join(item["normalized"] for item in palette)
        metadata = {
            "version": "0.4.1",
            "palette_version": data.get("paletteVersion", "unknown"),
            "dimensions": {"width": args.width, "height": args.height, "ratio": "3:4"},
            "palette_key": hashlib.sha256(palette_key_text.encode("utf-8")).hexdigest()[:16],
            "composition_seed": composition_seed,
            "weight_decay": args.decay,
            "grain": args.grain,
            "typography": typography,
            "flavors": [
                {**item, "weight": round(float(weights[i]), 6)}
                for i, item in enumerate(palette)
            ],
            "output": str(output),
        }
        metadata_path = output.with_suffix(".json")
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps({"png": str(output), "metadata": str(metadata_path), "seed": composition_seed}, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

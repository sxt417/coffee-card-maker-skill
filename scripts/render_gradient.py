#!/usr/bin/env python3
"""渲染带中文或英文文字的咖啡风味抽象艺术身份卡。"""

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
PROCESSING_PATH = SKILL_ROOT / "assets" / "processing-color-system.json"
ORIGIN_PATH = SKILL_ROOT / "assets" / "origin-color-adjustment.json"
COMPOSITION_PATH = SKILL_ROOT / "assets" / "composition-system.json"
SEMANTIC_PATH = SKILL_ROOT / "assets" / "flavor-semantic-system.json"
FONT_DIR = Path.home() / "Library" / "Fonts"
BUNDLED_FONT_DIR = SKILL_ROOT / "assets" / "fonts"
BUNDLED_FONTS = {
    ("en", "coffee"): BUNDLED_FONT_DIR / "PPEditorialNew-Regular.otf",
    ("en", "flavor"): BUNDLED_FONT_DIR / "SuisseIntlTrial-Medium.otf",
    ("zh", "coffee"): BUNDLED_FONT_DIR / "NotoSansCJKsc-Regular.otf",
    ("zh", "flavor"): BUNDLED_FONT_DIR / "NotoSansCJKsc-Regular.otf",
}
BUNDLED_CHINESE_BOLD_FONT = BUNDLED_FONT_DIR / "NotoSansCJKsc-Bold.otf"
BUNDLED_TEMPLATE_FONT = BUNDLED_FONT_DIR / "GoogleSansCode[MONO,wght].ttf"
PROCESSING_ICON_DIR = SKILL_ROOT / "assets" / "processing-icons"
PROCESSING_ICON_FILES = {
    "natural": PROCESSING_ICON_DIR / "natural.png",
    "washed": PROCESSING_ICON_DIR / "washed.png",
    "other": PROCESSING_ICON_DIR / "other.png",
}
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

DEFAULT_FLAVOR_WEIGHTS = np.array(
    [0.42, 0.25, 0.16, 0.10, 0.07, 0.045, 0.03, 0.02], dtype=np.float32
)

INTENSITY_PROFILES: dict[str, dict[str, float]] = {
    "soft": {
        "opacity": 0.82, "contrast": 0.78, "chroma": 0.88,
        "blur": 1.18, "grain": 0.72, "highlight": 1.18,
    },
    "balanced": {
        "opacity": 1.0, "contrast": 1.0, "chroma": 1.0,
        "blur": 1.0, "grain": 1.0, "highlight": 1.0,
    },
    "expressive": {
        "opacity": 1.12, "contrast": 1.2, "chroma": 1.1,
        "blur": 0.9, "grain": 1.15, "highlight": 0.88,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flavors", required=True, help="用逗号、斜杠、分号或中文顿号分隔的风味词")
    parser.add_argument("--language", choices=("en", "zh"), default="en", help="卡片文字版本：en 英文，zh 中文")
    parser.add_argument("--coffee-name", required=True, help="用于卡片展示的咖啡名称；语言须与 --language 一致")
    parser.add_argument("--display-flavors", required=True, help="用于卡片展示的风味词；语言须与 --language 一致")
    parser.add_argument("--processing-method", help="可选；处理法名称或别名。省略时从咖啡名称自动识别")
    parser.add_argument("--origin", help="可选；产地名称或别名。省略时从咖啡名称自动识别")
    parser.add_argument(
        "--template-style", choices=("classic", "info_panel"), default="classic",
        help="版式：classic 原有居中文字卡 / info_panel 上文下图信息模版",
    )
    parser.add_argument("--country", help="info_panel 必填；国家/国家地区名称，使用粗体显示")
    parser.add_argument("--processing-label", help="info_panel 可选；左下角处理法显示文案")
    parser.add_argument("--processing-icon", help="info_panel 可选；覆盖内置处理法图标的 PNG 文件")
    parser.add_argument("--template-font", help="info_panel 英文版可选；Google Sans Code 字体文件")
    parser.add_argument("--coffee-font", help="可选；指定标题字体文件，仍会严格校验字体身份")
    parser.add_argument("--flavor-font", help="可选；指定风味字体文件，仍会严格校验字体身份")
    parser.add_argument("--colors", help="可选；与风味顺序对应、以逗号分隔的 HEX 自定义颜色")
    parser.add_argument("--output", default="coffee-card.png", help="PNG 输出路径")
    parser.add_argument("--seed", type=int, help="构图种子；省略时随机生成")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1440)
    parser.add_argument("--grain", type=float, default=0.024)
    parser.add_argument(
        "--visual-intensity",
        choices=("soft", "balanced", "expressive"),
        default="balanced",
        help="构图强度：soft / balanced / expressive，默认 balanced",
    )
    parser.add_argument(
        "--gradient-style",
        choices=("semantic_fields", "airy_mesh"),
        default="semantic_fields",
        help="渐变风格：semantic_fields 语义色域 / airy_mesh 高明度空气网格，默认 semantic_fields",
    )
    parser.add_argument(
        "--floral-treatment",
        choices=("none", "contour", "surfaces_only"),
        default="none",
        help="兼容旧命令；当前纯渐变版本固定关闭所有语义图形",
    )
    parser.add_argument(
        "--max-quality-attempts", type=int, default=4,
        help="自动质检失败时的最大生成次数，默认 4",
    )
    parser.add_argument(
        "--decay", type=float, default=None,
        help=argparse.SUPPRESS,
    )
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

    return family == "Noto Sans CJK SC" and weight == "Regular"


def expected_font_label(language: str, role: str) -> str:
    if language == "en":
        return "PP Editorial New Regular" if role == "coffee" else "Suisse Intl Trial Medium"
    return "Noto Sans CJK SC Regular（思源黑体）"


def resolve_required_font(language: str, role: str, override: str | None) -> Path:
    if override:
        candidates = [Path(override).expanduser()]
    else:
        candidates = [BUNDLED_FONTS[(language, role)]]
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
        f"请检查 skill 内的 {BUNDLED_FONT_DIR}，安装字体到 {FONT_DIR}，"
        f"或用 {option} 指定字体文件；禁止使用替代字体。"
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


CJK_TITLE_NO_BREAK_TERMS = tuple(sorted({
    "二氧化碳浸渍", "去果皮日晒", "双重厌氧发酵", "双重发酵", "乳酸发酵",
    "厌氧发酵", "厌氧日晒", "厌氧水洗", "半水洗", "湿刨法", "蜜处理",
    "黑蜜处理", "红蜜处理", "黄蜜处理", "白蜜处理", "日晒", "水洗",
    "黑蜜", "红蜜", "黄蜜", "白蜜", "原生种", "铁皮卡", "黄波旁",
    "红波旁", "粉红波旁", "卡杜拉", "卡杜艾", "瑰夏", "波旁",
}, key=len, reverse=True))


def segment_compact_cjk_title(chunk: str) -> list[str]:
    """Keep known coffee terms intact inside Chinese titles without explicit spaces."""
    if not re.fullmatch(r"[\u3400-\u9fff]+", chunk) or len(chunk) <= 6:
        return [chunk]
    result: list[str] = []
    index = 0
    while index < len(chunk):
        matched = next(
            (term for term in CJK_TITLE_NO_BREAK_TERMS if chunk.startswith(term, index)),
            None,
        )
        if matched:
            result.append(matched)
            index += len(matched)
        else:
            result.append(chunk[index])
            index += 1
    return result


def tokenize_cjk_title(paragraph: str) -> list[tuple[str, bool]]:
    """Return (token, space_before) pairs; explicit title units stay unbreakable."""
    units = re.findall(r"\S+", normalize_mixed_cjk_spacing(paragraph))
    tokens: list[tuple[str, bool]] = []
    for unit_index, unit in enumerate(units):
        subtokens = segment_compact_cjk_title(unit)
        for sub_index, token in enumerate(subtokens):
            tokens.append((token, unit_index > 0 and sub_index == 0))
    return tokens


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
        tokens = tokenize_cjk_title(paragraph)
        current = ""
        for token, space_before in tokens:
            separator = " " if space_before and current else ""
            candidate = current + separator + token
            if tracked_width(draw, candidate, font, spacing) <= max_width:
                current = candidate
            elif current and tracked_width(draw, token, font, spacing) <= max_width:
                lines.append(current)
                current = token
            else:
                return None
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
            "line_break_policy": "semantic_units_no_split",
            "protected_terms": [
                term for term in CJK_TITLE_NO_BREAK_TERMS
                if language == "zh" and term in coffee_name
            ],
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


def load_info_panel_font(path: Path, size: int, weight: int) -> ImageFont.FreeTypeFont:
    """Load the exact Google Sans Code variable font used by the info-panel template."""
    if not path.is_file():
        raise FileNotFoundError(f"info_panel 缺少 Google Sans Code 字体：{path}")
    font = ImageFont.truetype(str(path), size=size)
    family, _ = font.getname()
    if family != "Google Sans Code":
        raise RuntimeError(f"info_panel 必须使用 Google Sans Code，实际为 {family}")
    try:
        font.set_variation_by_axes([weight, 1])
    except (AttributeError, OSError):
        # Pillow versions without variable-font support still load the regular
        # face; preserve correctness of the template instead of substituting.
        if weight >= 700:
            raise RuntimeError("当前 Pillow 不支持 Google Sans Code 的粗体可变轴")
    return font


def load_chinese_panel_font(size: int, weight: int) -> tuple[ImageFont.FreeTypeFont, Path]:
    """Load the bundled Noto Sans CJK SC face required by every Chinese text run."""
    font_path = BUNDLED_CHINESE_BOLD_FONT if weight >= 700 else BUNDLED_FONTS[("zh", "coffee")]
    expected_weight = "Bold" if weight >= 700 else "Regular"
    if not font_path.is_file():
        raise FileNotFoundError(f"中文版缺少思源黑体文件：{font_path}")
    try:
        font = ImageFont.truetype(str(font_path), size=size)
    except OSError as exc:
        raise RuntimeError(f"中文版思源黑体无法加载：{font_path}") from exc
    family, actual_weight = font.getname()
    if family != "Noto Sans CJK SC" or actual_weight != expected_weight:
        raise RuntimeError(
            f"中文版必须使用 Noto Sans CJK SC {expected_weight}，"
            f"实际为 {family} {actual_weight}"
        )
    return font, font_path


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def load_info_text_font(
    path: Path, size: int, weight: int, text: str, language: str,
) -> ImageFont.FreeTypeFont:
    """Use Noto Sans CJK SC throughout Chinese cards; keep Google Sans Code for English."""
    if language == "zh":
        return load_chinese_panel_font(size, weight)[0]
    if contains_cjk(text):
        raise ValueError("英文版 info_panel 不得包含未翻译的中文文字")
    return load_info_panel_font(path, size, weight)


def split_info_lines(
    draw: ImageDraw.ImageDraw, text: str, max_width: float,
    font_path: Path, size: int, weight: int, language: str, max_lines: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for candidate_size in range(size, max(24, round(size * 0.68)) - 1, -2):
        font = load_info_text_font(font_path, candidate_size, weight, text, language)
        wrapper = wrap_cjk if language == "zh" else wrap_words
        lines = wrapper(draw, text, font, 0, max_width)
        if lines and len(lines) <= max_lines:
            return font, lines
    raise ValueError("info_panel 文字无法在指定安全区域内排版")


def fit_info_flavor_lines(
    draw: ImageDraw.ImageDraw, flavors: list[str], max_width: float,
    font_path: Path, size: int, language: str,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Prefer one line across the full title-column width before allowing a wrap."""
    minimum_size = max(22, round(size * 0.72))
    one_line = " | ".join(flavors)
    for candidate_size in range(size, minimum_size - 1, -1):
        font = load_info_text_font(font_path, candidate_size, 400, " ".join(flavors), language)
        if draw.textlength(one_line, font=font) <= max_width:
            return font, [one_line]

    # Only wrap after the complete flavor string has failed at every allowed
    # single-line size. Break exclusively between flavor items.
    for candidate_size in range(size, minimum_size - 1, -1):
        font = load_info_text_font(font_path, candidate_size, 400, " ".join(flavors), language)
        candidates: list[tuple[float, list[str]]] = []
        for split_at in range(1, len(flavors)):
            lines = [" | ".join(flavors[:split_at]), " | ".join(flavors[split_at:])]
            widths = [draw.textlength(line, font=font) for line in lines]
            if max(widths) <= max_width:
                candidates.append((abs(widths[0] - widths[1]), lines))
        if candidates:
            return font, min(candidates, key=lambda item: item[0])[1]
    raise ValueError("info_panel 风味无法在两行安全区域内排版")


def draw_processing_icon(
    image: Image.Image, processing_key: str, icon_path: str | None, scale: float,
) -> str:
    cx, cy = 125 * scale, 125 * scale
    if icon_path:
        source = Path(icon_path).expanduser()
        if not source.is_file():
            raise FileNotFoundError(f"未找到指定的处理法图标：{source}")
        icon = Image.open(source).convert("RGBA")
        icon.thumbnail((150 * scale, 150 * scale), Image.Resampling.LANCZOS)
        image.alpha_composite(icon, (round(cx - icon.width / 2), round(cy - icon.height / 2)))
        return str(source)
    asset_key = processing_key if processing_key in ("natural", "washed") else "other"
    source = PROCESSING_ICON_FILES[asset_key]
    if not source.is_file():
        raise FileNotFoundError(f"缺少内置处理法图标：{source}")
    icon = Image.open(source).convert("RGBA")
    icon.thumbnail((150 * scale, 150 * scale), Image.Resampling.LANCZOS)
    image.alpha_composite(icon, (round(cx - icon.width / 2), round(cy - icon.height / 2)))
    return f"builtin:{asset_key}:{source.name}"


def processing_display_label(processing_key: str, label: str | None, language: str) -> str:
    if label:
        return label.strip()
    labels = {
        "natural": ("Natural", "日晒"), "washed": ("Washed", "水洗"),
        "honey": ("Honey", "蜜处理"), "anaerobic": ("Anaerobic", "厌氧发酵"),
        "carbonic_maceration": ("Carbonic Maceration", "二氧化碳浸渍"),
    }
    return labels.get(processing_key, ("Process", "处理法"))[1 if language == "zh" else 0]


def strip_leading_country(coffee_name: str, country: str) -> tuple[str, bool]:
    """Keep the bold country header from being repeated in the coffee-name block."""
    name = re.sub(r"\s+", " ", coffee_name).strip()
    country_name = re.sub(r"\s+", " ", country).strip()
    if not country_name or not name.casefold().startswith(country_name.casefold()):
        return name, False

    remainder = name[len(country_name):]
    if remainder and not contains_cjk(country_name):
        first = remainder[0]
        if not (first.isspace() or first in ",，:：/\\-–—·"):
            return name, False
    remainder = re.sub(r"^[\s,，:：/\\\-–—·]+", "", remainder).strip()
    if not remainder:
        return name, False
    return remainder, True


def fit_country_inline_name(
    draw: ImageDraw.ImageDraw,
    country: str,
    coffee_name: str,
    country_font: ImageFont.FreeTypeFont,
    name_font: ImageFont.FreeTypeFont,
    max_width: float,
) -> tuple[str, str]:
    """Fit complete leading name units after the bold country on the first line."""
    units = re.findall(r"\S+", normalize_mixed_cjk_spacing(coffee_name))
    if not units:
        return "", ""

    country_width = draw.textlength(country, font=country_font)
    spacer_width = draw.textlength(" ", font=name_font)
    available_width = max_width - country_width - spacer_width
    if available_width <= 0:
        return "", coffee_name

    inline_units: list[str] = []
    for unit in units:
        candidate = " ".join([*inline_units, unit])
        if draw.textlength(candidate, font=name_font) <= available_width:
            inline_units.append(unit)
        else:
            break

    if not inline_units:
        return "", coffee_name
    return " ".join(inline_units), " ".join(units[len(inline_units):])


def add_info_panel_typography(
    image: Image.Image, coffee_name: str, display_flavors: list[str], language: str,
    country: str, processing_key: str, processing_label: str | None,
    processing_icon: str | None, template_font_path: Path,
) -> dict[str, Any]:
    """Overlay the reference's 31.25% white information panel above the semantic gradient."""
    width, height = image.size
    scale = width / 1200
    panel_height = round(height * 0.3125)
    image.paste("#FFFFFF", (0, 0, width, panel_height))
    image_rgba = image.convert("RGBA")
    icon_source = draw_processing_icon(image_rgba, processing_key, processing_icon, scale)
    draw = ImageDraw.Draw(image_rgba)
    # Fixed reference grid: every text block keeps a 50 px outer inset.
    # The right information column is always x=600…1150 (550 px) on 1200 px.
    title_x, title_y = 600 * scale, 56 * scale
    title_width = 550 * scale
    display_coffee_name, country_removed = strip_leading_country(coffee_name, country)
    title_flow = None
    wrapper = wrap_cjk if language == "zh" else wrap_words
    for candidate_size in range(round(52 * scale), round(40 * scale) - 1, -2):
        candidate_name_font = load_info_text_font(
            template_font_path, candidate_size, 400, display_coffee_name, language
        )
        candidate_country_font = load_info_text_font(
            template_font_path, candidate_size, 700, country.strip(), language
        )
        candidate_inline, candidate_remaining = fit_country_inline_name(
            draw, country.strip(), display_coffee_name,
            candidate_country_font, candidate_name_font, title_width,
        )
        if not candidate_inline:
            continue
        candidate_lines = (
            wrapper(draw, candidate_remaining, candidate_name_font, 0, title_width)
            if candidate_remaining else []
        )
        if candidate_lines is not None and len(candidate_lines) <= 3:
            title_flow = (
                candidate_country_font, candidate_name_font,
                candidate_inline, candidate_remaining, candidate_lines,
            )
            break

    if title_flow is None:
        name_font, name_lines = split_info_lines(
            draw, display_coffee_name, title_width, template_font_path,
            round(52 * scale), 400, language, 3,
        )
        country_font = load_info_text_font(
            template_font_path, name_font.size, 700, country.strip(), language
        )
        inline_name, remaining_name = "", display_coffee_name
    else:
        country_font, name_font, inline_name, remaining_name, name_lines = title_flow

    title_line_advance = (70 if language == "zh" else 63) * scale
    draw.text((title_x, title_y), country.strip(), font=country_font, fill="#000000")
    if inline_name:
        inline_x = (
            title_x
            + draw.textlength(country.strip(), font=country_font)
            + draw.textlength(" ", font=name_font)
        )
        draw.text((inline_x, title_y), inline_name, font=name_font, fill="#000000")

    if remaining_name:
        if title_flow is None:
            name_lines = wrapper(draw, remaining_name, name_font, 0, title_width)
            if not name_lines or len(name_lines) > 3:
                raise ValueError("info_panel 咖啡名称无法在指定安全区域内排版")
    else:
        name_lines = []
    for index, line in enumerate(name_lines, start=1):
        draw.text(
            (title_x, title_y + index * title_line_advance),
            line, font=name_font, fill="#000000",
        )
    visible_title_lines = [
        country.strip() + (f" {inline_name}" if inline_name else ""),
        *name_lines,
    ]

    label = processing_display_label(processing_key, processing_label, language)
    label_font = load_info_text_font(template_font_path, round(45 * scale), 400, label, language)
    label_position = (50 * scale, 403 * scale)
    draw.text(label_position, label, font=label_font, fill="#000000")
    label_visual_bottom = draw.textbbox(label_position, label, font=label_font)[3]

    flavor_font, flavor_lines = fit_info_flavor_lines(
        draw, display_flavors, title_width, template_font_path, round(29 * scale), language
    )
    flavor_line_advance = 44 * scale
    last_flavor_bbox = draw.textbbox((0, 0), flavor_lines[-1], font=flavor_font)
    last_flavor_y = label_visual_bottom - last_flavor_bbox[3]
    flavor_y = last_flavor_y - (len(flavor_lines) - 1) * flavor_line_advance
    flavor_positions: list[list[float]] = []
    for index, line in enumerate(flavor_lines):
        position = (title_x, flavor_y + index * flavor_line_advance)
        draw.text(position, line, font=flavor_font, fill="#000000")
        flavor_positions.append([position[0], position[1]])
    image.paste(image_rgba.convert("RGB"))
    return {
        "template_style": "info_panel", "panel_height": panel_height, "panel_ratio": 0.3125,
        "text_inset": 50 * scale, "right_text_column": {"x": title_x, "width": title_width},
        "country": {
            "text": country.strip(), "font": country_font.getname()[0],
            "weight": ("700" if language == "en" else country_font.getname()[1]),
            "font_size": country_font.size, "position": [title_x, title_y],
            "inline_name": inline_name or None,
        },
        "coffee_name": {
            "input_text": coffee_name.strip(), "text": display_coffee_name,
            "country_prefix_removed": country_removed,
            "font": name_font.getname()[0],
            "weight": ("400" if language == "en" else name_font.getname()[1]),
            "font_size": name_font.size,
            "lines": ([inline_name] if inline_name else []) + name_lines,
            "visible_title_lines": visible_title_lines,
            "line_advance": title_line_advance,
            "layout_policy": "country_inline_with_complete_semantic_units",
        },
        "display_flavors": {
            "items": display_flavors, "font": flavor_font.getname()[0],
            "weight": ("400" if language == "en" else flavor_font.getname()[1]),
            "font_size": flavor_font.size,
            "lines": flavor_lines, "positions": flavor_positions,
            "available_width": title_width,
            "layout_policy": "full_title_column_single_line_before_wrap",
            "bottom_aligned_with_processing": True,
            "visual_bottom": label_visual_bottom,
        },
        "processing": {
            "key": processing_key, "label": label, "icon": icon_source,
            "font": label_font.getname()[0],
            "weight": ("400" if language == "en" else label_font.getname()[1]),
            "font_size": label_font.size,
            "visual_bottom": label_visual_bottom,
        },
        "font_files": (
            {
                "regular": str(BUNDLED_FONTS[("zh", "coffee")]),
                "bold": str(BUNDLED_CHINESE_BOLD_FONT),
            }
            if language == "zh"
            else {"regular_and_bold_variable": str(template_font_path)}
        ),
        "font_policy": (
            "all_chinese_text_uses_noto_sans_cjk_sc"
            if language == "zh"
            else "all_english_text_uses_google_sans_code"
        ),
        "cjk_fallback": None,
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


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_detection_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", " ", value.lower()).strip()


def alias_matches(text: str, alias: str) -> bool:
    normalized_text = f" {normalize_detection_text(text)} "
    normalized_alias = normalize_detection_text(alias)
    if not normalized_alias:
        return False
    if re.fullmatch(r"[a-z0-9 ]+", normalized_alias):
        return f" {normalized_alias} " in normalized_text
    return normalized_alias.replace(" ", "") in normalized_text.replace(" ", "")


def detect_profile(
    explicit: str | None,
    coffee_name: str,
    profiles: dict[str, Any],
    fallback: str,
    detection_order: list[str] | None = None,
) -> tuple[str, dict[str, Any], str]:
    order = detection_order or [key for key in profiles if key != fallback]
    if explicit:
        explicit_key = normalize_detection_text(explicit).replace(" ", "_")
        if explicit_key in profiles:
            return explicit_key, profiles[explicit_key], "explicit"
        for key in order:
            if any(alias_matches(explicit, alias) for alias in profiles[key].get("aliases", [])):
                return key, profiles[key], "explicit_alias"
        raise ValueError(f"无法识别指定值：{explicit}")

    for key in order:
        if any(alias_matches(coffee_name, alias) for alias in profiles[key].get("aliases", [])):
            return key, profiles[key], "coffee_name"
    return fallback, profiles[fallback], "fallback"


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
        family = infer_family(norm)
        item = resolve_one(
            original,
            data,
            by_id,
            alias_to_id,
            longest_aliases,
            fallback_family=family,
        )
        if overrides:
            item["palette_source"] = item.get("source")
            item["source"] = "override"
            item["primary"] = normalize_hex(overrides[i])
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


def compute_weights(count: int, decay: float | None = None) -> np.ndarray:
    """Return the 2.0 semantic weights; the legacy decay flag is ignored on purpose."""
    if not 2 <= count <= len(DEFAULT_FLAVOR_WEIGHTS):
        raise ValueError("风味数量必须介于 2 和 8 之间")
    raw = DEFAULT_FLAVOR_WEIGHTS[:count].copy()
    return raw / raw.sum()


def semantic_category(family: str) -> str:
    return {
        "floral": "floral",
        "citrus": "citrus",
        "berry": "berry",
        "dried_fruit": "berry",
        "orchard_stone": "stone_fruit",
        "tropical_melon": "tropical",
        "tea_herbal": "tea_herbal",
        "nuts_cocoa": "chocolate_nut",
        "sweet_bakery": "chocolate_nut",
        "spice": "chocolate_nut",
        "roasted_woody": "chocolate_nut",
        "boozy_fermented": "fermented_winey",
        "override": "tropical",
    }.get(family, "tropical")


def enrich_semantic_palette(
    palette: list[dict[str, Any]], semantic_data: dict[str, Any]
) -> list[dict[str, Any]]:
    shape_languages = semantic_data.get("shape_languages", {})
    enriched: list[dict[str, Any]] = []
    for item in palette:
        category = semantic_category(str(item.get("family", "")))
        shape = shape_languages.get(category, shape_languages.get("tropical", {}))
        body = normalize_hex(item.get("primary", item["hex"]))
        if item.get("source") == "override":
            body_lab = linear_srgb_to_oklab(srgb_to_linear(hex_to_srgb(body)))
            core_lab = body_lab.copy()
            core_lab[0] = np.clip(core_lab[0] - 0.18, 0.18, 0.82)
            core_lab[1:3] *= 1.08
            highlight_lab = body_lab.copy()
            highlight_lab[0] = np.clip(highlight_lab[0] + 0.16, 0.72, 0.98)
            highlight_lab[1:3] *= 0.52
            core = srgb_to_hex(linear_to_srgb(oklab_to_linear_srgb(core_lab)))
            highlight = srgb_to_hex(linear_to_srgb(oklab_to_linear_srgb(highlight_lab)))
        else:
            core = normalize_hex(item.get("dark", body))
            highlight = normalize_hex(item.get("light", body))
        enriched.append({
            **item,
            "hex": body,
            "category": category,
            "palette": {"core": core, "body": body, "highlight": highlight},
            "shape_language": shape.get("forms", ["fluid irregular field"])[0],
            "shape_profile": shape,
        })
    return enriched


def circular_hue_distance(first: np.ndarray, second: np.ndarray) -> float:
    h1 = math.atan2(float(first[2]), float(first[1]))
    h2 = math.atan2(float(second[2]), float(second[1]))
    return abs(math.atan2(math.sin(h1 - h2), math.cos(h1 - h2)))


def cluster_semantic_fields(
    palette: list[dict[str, Any]], weights: np.ndarray
) -> tuple[list[dict[str, Any]], np.ndarray, list[int]]:
    """Merge near colors into two-to-four perceptual fields without losing provenance."""
    labs = np.stack([
        linear_srgb_to_oklab(srgb_to_linear(hex_to_srgb(item["palette"]["body"])))
        for item in palette
    ])
    fruit_categories = {"citrus", "berry", "stone_fruit", "tropical"}
    clusters: list[dict[str, Any]] = []
    mapping: list[int] = []
    for index, (item, lab) in enumerate(zip(palette, labs)):
        best: tuple[float, int] | None = None
        for cluster_index, cluster in enumerate(clusters):
            category_close = (
                item["category"] == cluster["category"]
                or {item["category"], cluster["category"]} <= fruit_categories
            )
            hue_distance = circular_hue_distance(lab, cluster["body_lab"])
            lightness_distance = abs(float(lab[0] - cluster["body_lab"][0]))
            if category_close and hue_distance <= math.radians(32) and lightness_distance <= 0.18:
                score = hue_distance + lightness_distance
                if best is None or score < best[0]:
                    best = (score, cluster_index)
        if best is None:
            clusters.append({
                "category": item["category"], "members": [index],
                "weight": float(weights[index]), "body_lab": lab.copy(),
            })
            mapping.append(len(clusters) - 1)
        else:
            cluster_index = best[1]
            cluster = clusters[cluster_index]
            total = cluster["weight"] + float(weights[index])
            cluster["body_lab"] = (
                cluster["body_lab"] * cluster["weight"] + lab * float(weights[index])
            ) / total
            cluster["weight"] = total
            cluster["members"].append(index)
            mapping.append(cluster_index)

    while len(clusters) > 4:
        candidates: list[tuple[float, int, int]] = []
        for i in range(1, len(clusters)):
            for j in range(i + 1, len(clusters)):
                distance = float(np.linalg.norm(clusters[i]["body_lab"] - clusters[j]["body_lab"]))
                candidates.append((distance, i, j))
        _, target, source = min(candidates)
        a, b = clusters[target], clusters[source]
        total = a["weight"] + b["weight"]
        a["body_lab"] = (a["body_lab"] * a["weight"] + b["body_lab"] * b["weight"]) / total
        a["weight"] = total
        a["members"].extend(b["members"])
        clusters.pop(source)
        mapping = [target if value == source else value - (value > source) for value in mapping]

    fields: list[dict[str, Any]] = []
    for cluster_index, cluster in enumerate(clusters):
        member_indexes = cluster["members"]
        member_weights = np.array([weights[i] for i in member_indexes], dtype=np.float32)
        member_weights /= member_weights.sum()
        triad: dict[str, str] = {}
        for tone in ("core", "body", "highlight"):
            tone_labs = np.stack([
                linear_srgb_to_oklab(srgb_to_linear(hex_to_srgb(palette[i]["palette"][tone])))
                for i in member_indexes
            ])
            mixed = np.einsum("n,nc->c", member_weights, tone_labs)
            triad[tone] = srgb_to_hex(linear_to_srgb(oklab_to_linear_srgb(mixed)))
        lead_index = member_indexes[0]
        fields.append({
            **palette[lead_index],
            "hex": triad["body"],
            "palette": triad,
            "cluster_index": cluster_index,
            "member_indexes": member_indexes,
            "member_flavors": [palette[i].get("input") for i in member_indexes],
            "cluster_weight": round(float(cluster["weight"]), 6),
        })
    cluster_weights = np.array([cluster["weight"] for cluster in clusters], dtype=np.float32)
    cluster_weights /= cluster_weights.sum()
    return fields, cluster_weights, mapping


def select_semantic_shapes(
    fields: list[dict[str, Any]], mapping: list[int], intensity: str,
    floral_treatment: str = "contour",
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used: set[int] = set()
    for flavor_index in range(len(mapping)):
        field_index = mapping[flavor_index]
        if field_index in used:
            continue
        field = fields[field_index]
        profile = field.get("shape_profile", {})
        forms = profile.get("forms", ["fluid irregular field"])
        role = "main" if not selected else "auxiliary"
        selected.append({
            "flavor_index": field_index,
            "source_flavor_index": flavor_index,
            "flavor": field.get("input"),
            "motif_key": field.get("category"),
            "shape": {
                "floral": "radial_petals", "citrus": "translucent_rings",
                "berry": "cluster_blobs", "stone_fruit": "organic_pulp",
                "tropical": "liquid_bloom", "tea_herbal": "mist_ribbon",
                "chocolate_nut": "organic_pulp", "fermented_winey": "liquid_bloom",
            }.get(field.get("category"), "liquid_bloom"),
            "shape_language": forms[0],
            "forms": forms,
            "motion": profile.get("motion", "drifting"),
            "density": profile.get("density", "medium"),
            "edge": profile.get("edge", "very_soft"),
            "semantic_opacity": 0.34 if intensity == "soft" else 0.46 if intensity == "expressive" else 0.4,
            "role": role,
            "renderer": {
                "scale": (
                    0.78 if role == "main" and field.get("category") == "floral"
                    else 0.9 if role == "main"
                    else 0.72
                ),
                "density": 5 if role == "main" else 3,
                "blur": 0.09 if intensity == "soft" else 0.07,
                "lightness_shift": 0.08 if role == "main" else 0.05,
                "contour_blur": 0.010 if intensity == "soft" else 0.009,
                "contour_opacity": (
                    0.44 if intensity == "soft"
                    else 0.48 if intensity == "expressive"
                    else 0.44
                ),
                "contour_lightness_delta": 0.22 if role == "main" else 0.12,
                "contour_enabled": floral_treatment == "contour",
            },
        })
        used.add(field_index)
        if len(selected) == 2:
            break
    return selected


def resolve_flavor_hierarchy(
    flavors: list[str],
    palette: list[dict[str, Any]],
    weights: np.ndarray,
    composition_data: dict[str, Any],
) -> dict[str, Any]:
    """Classify the sensory weight without changing the deterministic flavor hues."""
    hierarchy = composition_data.get("flavor_hierarchy", {})
    scores = {key: 0.0 for key in ("light", "medium", "heavy")}
    normalized_flavors = [normalize_word(item) for item in flavors]
    for index, item in enumerate(palette):
        family = item.get("family")
        for level, profile in hierarchy.items():
            family_match = family in profile.get("families", [])
            keyword_match = any(
                keyword.lower() in normalized_flavors[index]
                for keyword in profile.get("keywords", [])
            )
            if family_match or keyword_match:
                scores[level] = scores.get(level, 0.0) + float(weights[index])

    first_family = palette[0].get("family") if palette else None
    heavy_families = set(hierarchy.get("heavy", {}).get("families", []))
    light_families = set(hierarchy.get("light", {}).get("families", []))
    if first_family in heavy_families or scores.get("heavy", 0.0) >= 0.28:
        level = "heavy"
    elif first_family in light_families and scores.get("light", 0.0) >= 0.48:
        level = "light"
    else:
        level = max(scores, key=scores.get) if any(scores.values()) else "medium"
    profile = hierarchy.get(level, hierarchy.get("medium", {}))
    return {
        "level": level,
        "scores": {key: round(value, 6) for key, value in scores.items()},
        **profile,
    }


def select_composition(
    processing_key: str,
    palette: list[dict[str, Any]],
    weights: np.ndarray,
    hierarchy: dict[str, Any],
    composition_data: dict[str, Any],
    composition_seed: int,
) -> dict[str, Any]:
    """Choose one traceable art direction, then vary it deterministically with the seed."""
    styles = composition_data.get("styles", {})
    if not styles:
        raise ValueError("构图系统缺少 styles 配置")
    scores: dict[str, float] = {}
    for key, style in styles.items():
        score = 2.0 if processing_key in style.get("preferred_processing", []) else 0.0
        preferred_families = set(style.get("preferred_families", []))
        score += sum(
            float(weights[index]) * 2.4
            for index, item in enumerate(palette)
            if item.get("family") in preferred_families
        )
        if hierarchy.get("level") == "light" and key == "soft_bloom":
            score += 0.8
        elif hierarchy.get("level") == "heavy" and key in {"mineral_texture", "color_collision"}:
            score += 0.7
        scores[key] = score

    best_score = max(scores.values())
    candidates = [key for key, score in scores.items() if score >= best_score - 0.35]
    choice_rng = np.random.default_rng(composition_seed ^ stable_int(processing_key, 4))
    style_key = candidates[int(choice_rng.integers(0, len(candidates)))]
    style = styles[style_key]
    organic = composition_data.get("organic_blob_system", {})
    configured_range = style.get("blob_count", [3, 5])
    minimum = max(int(organic.get("minimum_blobs", 3)), int(configured_range[0]))
    maximum = min(int(organic.get("maximum_blobs", 5)), int(configured_range[1]))
    blob_count = int(choice_rng.integers(minimum, maximum + 1))
    blur_range = organic.get("blur_radius_px", [80, 200])
    opacity_range = organic.get("opacity", [0.34, 0.68])
    texture_config = composition_data.get("material_texture", {})
    texture_opacity_range = texture_config.get("opacity", [0.1, 0.15])
    return {
        "key": style_key,
        "label": style.get("label", style_key),
        "visual_language": style.get("visual_language"),
        "flow_bias": style.get("flow_bias", "radial"),
        "aspect_ratio": style.get("aspect_ratio", [0.8, 1.8]),
        "edge_crop_probability": float(style.get("edge_crop_probability", 0.6)),
        "blob_count": blob_count,
        "blur_radius_px": [float(blur_range[0]), float(blur_range[1])],
        "opacity": [float(opacity_range[0]), float(opacity_range[1])],
        "texture_opacity": float(choice_rng.uniform(texture_opacity_range[0], texture_opacity_range[1])),
        "selection_scores": {key: round(value, 6) for key, value in scores.items()},
        "hierarchy": hierarchy,
    }


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


def srgb_to_hex(rgb: np.ndarray) -> str:
    channels = np.uint8(np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5)
    return "#" + "".join(f"{int(channel):02X}" for channel in channels)


def apply_chromatic_system(
    palette: list[dict[str, Any]],
    processing: dict[str, Any],
    origin: dict[str, Any],
) -> list[dict[str, Any]]:
    """Keep flavor as the hue source while processing controls its visual personality."""
    processing_palette = processing.get("palette", [])
    processing_renderer = processing.get("renderer", {})
    origin_renderer = origin.get("renderer", {})
    transformed: list[dict[str, Any]] = []

    for index, item in enumerate(palette):
        base_hex = normalize_hex(item["hex"])
        base_lab = linear_srgb_to_oklab(srgb_to_linear(hex_to_srgb(base_hex)))
        adjusted = base_lab.copy()
        undertone_hex: str | None = None

        if processing_palette:
            undertone_labs = np.stack([
                linear_srgb_to_oklab(srgb_to_linear(hex_to_srgb(normalize_hex(value))))
                for value in processing_palette
            ])
            base_chroma = base_lab[1:3]
            undertone_chroma = undertone_labs[:, 1:3]
            similarity = undertone_chroma @ base_chroma / np.maximum(
                np.linalg.norm(undertone_chroma, axis=1) * np.linalg.norm(base_chroma),
                1e-6,
            )
            undertone_index = int(np.argmax(similarity))
            undertone_hex = normalize_hex(processing_palette[undertone_index])
            undertone_lab = undertone_labs[undertone_index]
            influence = float(processing_renderer.get("palette_influence", 0.0))
            adjusted = adjusted * (1.0 - influence) + undertone_lab * influence

        adjusted[1:3] *= float(processing_renderer.get("chroma_scale", 1.0))
        adjusted[0] += float(processing_renderer.get("lightness_shift", 0.0))
        adjusted[2] += float(processing_renderer.get("temperature_shift", 0.0))

        accent_influence = float(origin_renderer.get("accent_influence", 0.0))
        if accent_influence > 0 and origin.get("accent"):
            accent_lab = linear_srgb_to_oklab(
                srgb_to_linear(hex_to_srgb(normalize_hex(origin["accent"])))
            )
            adjusted = adjusted * (1.0 - accent_influence) + accent_lab * accent_influence
        adjusted[1:3] *= float(origin_renderer.get("chroma_scale", 1.0))
        adjusted[0] += float(origin_renderer.get("lightness_shift", 0.0))
        adjusted[2] += float(origin_renderer.get("temperature_shift", 0.0))

        adjusted[0] = np.clip(adjusted[0], 0.2, 0.94)
        effective_rgb = linear_to_srgb(oklab_to_linear_srgb(adjusted))
        transformed.append({
            **item,
            "base_hex": base_hex,
            "hex": srgb_to_hex(effective_rgb),
            "processing_undertone": undertone_hex,
        })
    return transformed


def protect_color_clarity(
    canvas_lab: np.ndarray,
    mix_weights: np.ndarray,
    palette_lab: np.ndarray,
) -> np.ndarray:
    """Restore chroma lost to cross-hue mixing without rotating the resulting hue."""
    palette_chroma = np.linalg.norm(palette_lab[:, 1:3], axis=1)
    expected_chroma = np.einsum("nhw,n->hw", mix_weights, palette_chroma, optimize=True)
    actual_chroma = np.linalg.norm(canvas_lab[..., 1:3], axis=2)

    chroma_floor = np.minimum(expected_chroma * 0.68, 0.16)
    eligible = (
        (canvas_lab[..., 0] > 0.25)
        & (canvas_lab[..., 0] < 0.88)
        & (expected_chroma > 0.045)
        & (actual_chroma < chroma_floor)
    )
    scale = np.where(
        eligible,
        np.minimum(chroma_floor / np.maximum(actual_chroma, 1e-6), 2.2),
        1.0,
    )
    canvas_lab[..., 1:3] *= scale[..., None]
    collapsed = eligible & (actual_chroma < 1e-4)
    if np.any(collapsed):
        dominant_ab = palette_lab[np.argmax(mix_weights, axis=0), 1:3]
        dominant_norm = np.linalg.norm(dominant_ab, axis=2, keepdims=True)
        restored_ab = dominant_ab / np.maximum(dominant_norm, 1e-6) * chroma_floor[..., None]
        canvas_lab[..., 1:3] = np.where(collapsed[..., None], restored_ab, canvas_lab[..., 1:3])
    return canvas_lab


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


def blur_motif_field(field: np.ndarray, blur_ratio: float) -> np.ndarray:
    field = field / max(float(field.max()), 1e-6)
    image = Image.fromarray(np.uint8(np.clip(field, 0.0, 1.0) * 255), mode="L")
    if blur_ratio > 0:
        image = image.filter(ImageFilter.GaussianBlur(max(1.0, image.width * blur_ratio)))
    blurred = np.asarray(image, dtype=np.float32) / 255.0
    return blurred / max(float(blurred.max()), 1e-6)


def build_motif_field(
    shape: str,
    X: np.ndarray,
    Y: np.ndarray,
    rng: np.random.Generator,
    scale: float,
    density: int,
    anchor_side: int,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Build only oversized, cropped, soft abstract fields—never literal objects."""
    side = -1 if anchor_side < 0 else 1
    cx = rng.uniform(0.03, 0.16) if side < 0 else rng.uniform(0.84, 0.97)
    cy = rng.uniform(0.18, 0.82)
    field = np.zeros_like(X, dtype=np.float32)
    contour_field: np.ndarray | None = None

    if shape == "radial_petals":
        cx = rng.uniform(0.14, 0.26) if side < 0 else rng.uniform(0.74, 0.86)
        cy = rng.uniform(0.24, 0.76)
        contour_field = np.zeros_like(X, dtype=np.float32)
        base_angle = rng.uniform(-math.pi, math.pi)
        for index in range(max(5, density)):
            angle = base_angle + index * math.tau / max(5, density)
            px = cx + math.cos(angle) * scale * 0.2
            py = cy + math.sin(angle) * scale * 0.16
            petal = elliptical_field(
                X, Y, px, py, scale * 0.34, scale * 0.11,
                angle, rng.uniform(1.6, 2.2),
            )
            field += petal
            # A wide iso-value band suggests a petal edge without drawing a line.
            contour_field += np.exp(-np.square((petal - 0.42) / 0.15))
        # Remove one broad angular sector so the flower can never become a
        # complete closed emblem. The remaining edge enters from the canvas side.
        theta = np.arctan2(Y - cy, X - cx)
        gap_angle = rng.uniform(-math.pi, math.pi)
        broken_arc_mask = np.clip(
            0.18 + 0.82 * (0.5 + 0.5 * np.cos(theta - gap_angle)), 0.0, 1.0
        )
        contour_field *= broken_arc_mask
    elif shape == "organic_pulp":
        for index in range(max(2, density)):
            field += elliptical_field(
                X, Y,
                cx + rng.uniform(-0.12, 0.12) * scale,
                cy + rng.uniform(-0.10, 0.10) * scale,
                scale * rng.uniform(0.38, 0.56),
                scale * rng.uniform(0.26, 0.42),
                rng.uniform(-math.pi, math.pi),
                rng.uniform(1.4, 2.0),
            )
    elif shape == "seed_burst":
        field += elliptical_field(X, Y, cx, cy, scale * 0.22, scale * 0.18, 0.0, 1.8) * 0.45
        for _ in range(max(24, density)):
            angle = rng.uniform(-math.pi, math.pi)
            radius = scale * np.clip(rng.normal(0.26, 0.12), 0.04, 0.52)
            px = cx + math.cos(angle) * radius
            py = cy + math.sin(angle) * radius * 0.82
            point_scale = scale * rng.uniform(0.018, 0.045)
            field += elliptical_field(
                X, Y, px, py, point_scale, point_scale * rng.uniform(0.65, 1.25),
                angle, rng.uniform(1.5, 2.4),
            ) * rng.uniform(0.35, 0.9)
    elif shape == "cluster_blobs":
        for _ in range(max(5, density)):
            angle = rng.uniform(-math.pi, math.pi)
            radius = scale * rng.uniform(0.03, 0.3)
            blob = scale * rng.uniform(0.12, 0.22)
            field += elliptical_field(
                X, Y,
                cx + math.cos(angle) * radius,
                cy + math.sin(angle) * radius * 0.8,
                blob, blob * rng.uniform(0.82, 1.2), angle, 1.9,
            )
    elif shape == "translucent_rings":
        dx = X - cx
        dy = (Y - cy) / 0.82
        radius = np.sqrt(dx * dx + dy * dy)
        for index in range(max(2, density)):
            ring_radius = scale * (0.2 + index * 0.12)
            ring_width = scale * rng.uniform(0.025, 0.055)
            field += np.exp(-((radius - ring_radius) / max(ring_width, 1e-4)) ** 2)
        angular_fade = 0.58 + 0.42 * np.cos(np.arctan2(dy, dx) - rng.uniform(-math.pi, math.pi))
        field *= np.clip(angular_fade, 0.0, 1.0)
    elif shape in {"mist_ribbon", "viscous_flow"}:
        ribbon_count = max(2, density)
        for index in range(ribbon_count):
            phase = rng.uniform(-math.pi, math.pi)
            frequency = rng.uniform(2.0, 4.2) if shape == "mist_ribbon" else rng.uniform(1.2, 2.4)
            amplitude = scale * (0.08 if shape == "mist_ribbon" else 0.13)
            centerline = cy + (index - (ribbon_count - 1) / 2) * scale * 0.1
            centerline += amplitude * np.sin(X * frequency * math.pi + phase)
            width = scale * (0.045 if shape == "mist_ribbon" else 0.085)
            x_fade = np.exp(-((X - cx) / max(scale * 0.82, 1e-4)) ** 2)
            field += np.exp(-((Y - centerline) / max(width, 1e-4)) ** 2) * x_fade
    elif shape == "liquid_bloom":
        base_angle = rng.uniform(-math.pi, math.pi)
        for index in range(max(4, density)):
            angle = base_angle + index * 1.35
            radius = scale * (0.05 + 0.055 * index)
            field += elliptical_field(
                X, Y,
                cx + math.cos(angle) * radius,
                cy + math.sin(angle) * radius * 0.8,
                scale * rng.uniform(0.16, 0.3),
                scale * rng.uniform(0.1, 0.22),
                angle + 0.6, rng.uniform(1.5, 2.2),
            )
    else:
        field = elliptical_field(X, Y, cx, cy, scale * 0.5, scale * 0.36, 0.0, 1.8)

    return field, contour_field


def apply_flavor_motifs(
    canvas_lab: np.ndarray,
    X: np.ndarray,
    Y: np.ndarray,
    palette_lab: np.ndarray,
    selected_motifs: list[dict[str, Any]],
    processing_renderer: dict[str, Any],
    visibility_rules: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    if not selected_motifs:
        raise ValueError("每张卡必须至少包含一个抽象风味母题")
    motif_strength = float(np.clip(
        0.8 + 0.28 * float(processing_renderer.get("contrast_scale", 1.0)),
        0.82,
        1.2,
    ))
    minimum_peak_alpha = float(visibility_rules.get("minimum_peak_alpha", 0.34))
    minimum_coverage = float(visibility_rules.get("minimum_visible_coverage", 0.08))
    visible_threshold = float(visibility_rules.get("visible_alpha_threshold", 0.12))
    minimum_lightness_delta = float(visibility_rules.get("minimum_lightness_delta", 0.14))
    minimum_contour_peak = float(visibility_rules.get("minimum_contour_peak_alpha", 0.16))
    minimum_contour_coverage = float(visibility_rules.get("minimum_contour_coverage", 0.025))
    minimum_contour_delta = float(visibility_rules.get("minimum_contour_lightness_delta", 0.07))
    minimum_contour_effective_contrast = float(
        visibility_rules.get("minimum_contour_effective_contrast", 0.05)
    )
    minimum_contour_score = float(visibility_rules.get("minimum_semantic_contour_score", 0.75))
    diagnostics: list[dict[str, Any]] = []
    main_side = -1 if rng.random() < 0.5 else 1
    for motif in selected_motifs:
        params = motif.get("renderer", {})
        field, contour_field = build_motif_field(
            motif["shape"], X, Y, rng,
            float(params.get("scale", 0.7)),
            int(params.get("density", 5)),
            main_side if motif["role"] == "main" else -main_side,
        )
        field = blur_motif_field(field, float(params.get("blur", 0.04)))
        role_scale = 1.0 if motif["role"] == "main" else 0.86
        opacity = max(
            float(motif.get("semantic_opacity", params.get("opacity", 0.4))) * 0.78,
            minimum_peak_alpha / max(role_scale * motif_strength, 1e-6),
        )
        alpha = np.clip(
            field * opacity * role_scale * motif_strength,
            0.0,
            0.56,
        )[..., None]
        for _ in range(8):
            if float(np.mean(alpha[..., 0] >= visible_threshold)) >= minimum_coverage:
                break
            field = np.power(np.clip(field, 0.0, 1.0), 0.68)
            alpha = np.clip(
                field * opacity * role_scale * motif_strength,
                0.0,
                0.56,
            )[..., None]
        motif_color = palette_lab[int(motif["flavor_index"])].copy()
        active = field >= 0.25
        local_lightness = (
            float(np.mean(canvas_lab[..., 0][active]))
            if np.any(active)
            else float(np.mean(canvas_lab[..., 0]))
        )
        requested_shift = float(params.get("lightness_shift", 0.0))
        direction = (
            1.0 if requested_shift > 0
            else -1.0 if requested_shift < 0
            else (1.0 if local_lightness < 0.62 else -1.0)
        )
        target_lightness = float(motif_color[0]) + requested_shift
        if abs(target_lightness - local_lightness) < minimum_lightness_delta:
            target_lightness = local_lightness + direction * minimum_lightness_delta
        target_lightness = float(np.clip(target_lightness, 0.16, 0.97))
        if abs(target_lightness - local_lightness) < minimum_lightness_delta:
            candidates = [
                float(np.clip(local_lightness + minimum_lightness_delta, 0.16, 0.97)),
                float(np.clip(local_lightness - minimum_lightness_delta, 0.16, 0.97)),
            ]
            preferred = 0 if direction > 0 else 1
            target_lightness = max(
                enumerate(candidates),
                key=lambda item: (abs(item[1] - local_lightness), item[0] == preferred),
            )[1]
        motif_color[0] = target_lightness
        actual_lightness_delta = abs(float(motif_color[0]) - local_lightness)
        canvas_lab = canvas_lab * (1.0 - alpha) + motif_color * alpha
        contour_enabled = bool(params.get("contour_enabled", True))
        contour_diagnostics = {
            "required": motif.get("motif_key") == "floral" and contour_enabled,
            "peak_alpha": 0.0,
            "visible_coverage": 0.0,
            "lightness_delta": 0.0,
            "effective_contrast": 0.0,
            "semantic_contour_score": 1.0,
            "visibility_passed": True,
        }
        if contour_field is not None and contour_enabled:
            contour_field = blur_motif_field(
                contour_field, float(params.get("contour_blur", 0.018))
            )
            contour_opacity = float(params.get("contour_opacity", 0.34))
            contour_alpha = np.clip(
                contour_field * contour_opacity * role_scale,
                0.0,
                0.44,
            )[..., None]
            contour_active = contour_field >= 0.28
            contour_local_lightness = (
                float(np.mean(canvas_lab[..., 0][contour_active]))
                if np.any(contour_active)
                else float(np.mean(canvas_lab[..., 0]))
            )
            requested_contour_delta = float(params.get("contour_lightness_delta", 0.09))
            contour_color = palette_lab[int(motif["flavor_index"])].copy()
            if contour_local_lightness >= 0.58:
                contour_color[0] = contour_local_lightness - requested_contour_delta
            else:
                contour_color[0] = contour_local_lightness + requested_contour_delta
            contour_color[0] = float(np.clip(contour_color[0], 0.18, 0.96))
            contour_color[1:3] *= 1.16
            actual_contour_delta = abs(
                float(contour_color[0]) - contour_local_lightness
            )
            canvas_lab = (
                canvas_lab * (1.0 - contour_alpha)
                + contour_color * contour_alpha
            )
            contour_peak = float(contour_alpha.max())
            contour_coverage = float(
                np.mean(contour_alpha[..., 0] >= 0.06)
            )
            contour_score = float(np.clip(
                0.25 * min(contour_peak / max(minimum_contour_peak, 1e-6), 1.0)
                + 0.25 * min(contour_coverage / max(minimum_contour_coverage, 1e-6), 1.0)
                + 0.25 * min(actual_contour_delta / max(minimum_contour_delta, 1e-6), 1.0)
                + 0.25 * min(
                    (contour_peak * actual_contour_delta)
                    / max(minimum_contour_effective_contrast, 1e-6),
                    1.0,
                ),
                0.0,
                1.0,
            ))
            effective_contour_contrast = contour_peak * actual_contour_delta
            contour_passed = bool(
                contour_peak >= minimum_contour_peak - 1e-4
                and contour_coverage >= minimum_contour_coverage
                and actual_contour_delta >= minimum_contour_delta - 1e-4
                and effective_contour_contrast >= minimum_contour_effective_contrast - 1e-4
                and contour_score >= minimum_contour_score - 1e-4
            )
            contour_diagnostics = {
                "required": motif.get("motif_key") == "floral" and contour_enabled,
                "peak_alpha": round(contour_peak, 4),
                "visible_coverage": round(contour_coverage, 4),
                "lightness_delta": round(actual_contour_delta, 4),
                "effective_contrast": round(effective_contour_contrast, 4),
                "semantic_contour_score": round(contour_score, 4),
                "visibility_passed": contour_passed,
            }
        visible_coverage = float(np.mean(alpha[..., 0] >= visible_threshold))
        peak_alpha = float(alpha.max())
        diagnostics.append({
            "role": motif["role"],
            "motif_key": motif["motif_key"],
            "peak_alpha": round(peak_alpha, 4),
            "visible_coverage": round(visible_coverage, 4),
            "lightness_delta": round(actual_lightness_delta, 4),
            "contour": contour_diagnostics,
            "visibility_passed": bool(
                peak_alpha >= minimum_peak_alpha - 1e-4
                and visible_coverage >= minimum_coverage
                and actual_lightness_delta >= minimum_lightness_delta - 1e-4
                and (
                    not contour_diagnostics["required"]
                    or contour_diagnostics["visibility_passed"]
                )
            ),
        })
    if not all(item["visibility_passed"] for item in diagnostics):
        raise ValueError(f"抽象风味母题未达到最低可见性要求：{diagnostics}")
    return canvas_lab, diagnostics


def render(
    palette: list[dict[str, Any]],
    weights: np.ndarray,
    width: int,
    height: int,
    composition_seed: int,
    grain_strength: float,
    processing_renderer: dict[str, Any],
    selected_motifs: list[dict[str, Any]],
    motif_visibility: dict[str, Any],
    composition: dict[str, Any],
    intensity_profile: dict[str, float],
    gradient_style: str = "semantic_fields",
    gradient_style_config: dict[str, Any] | None = None,
) -> tuple[Image.Image, list[dict[str, Any]], dict[str, Any]]:
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
    warp_scale = float(processing_renderer.get("warp_scale", 1.0))
    diffusion_scale = float(processing_renderer.get("diffusion_scale", 1.0))
    contrast_scale = float(intensity_profile.get("contrast", 1.0))
    grain_scale = float(intensity_profile.get("grain", 1.0))
    texture_mode = str(processing_renderer.get("texture_mode", "matte_grain"))
    warp_amount = rng.uniform(0.035, 0.085) * warp_scale
    Xw = X + curl_x * warp_amount
    Yw = Y + curl_y * warp_amount * 0.82

    airy_mesh = gradient_style == "airy_mesh"
    airy_config = gradient_style_config or {}
    fields = [
        np.full(
            (work_height, work_width),
            (0.010 if airy_mesh else 0.025) + float(weight) * (0.035 if airy_mesh else 0.08),
            dtype=np.float32,
        )
        for weight in weights
    ]
    blob_layers: list[tuple[np.ndarray, int, float]] = []
    max_weight = float(weights.max())
    hierarchy_profile = composition.get("hierarchy", {})
    if airy_mesh:
        anchor_range = airy_config.get("mesh_anchor_count", [5, 7])
        blob_count = int(rng.integers(int(anchor_range[0]), int(anchor_range[1]) + 1))
        blob_count = int(np.clip(blob_count, 5, 6))
    else:
        blob_count = int(np.clip(composition.get("blob_count", 4), 3, 5))
    assignment = list(range(min(len(weights), blob_count)))
    while len(assignment) < blob_count:
        assignment.append(int(rng.choice(len(weights), p=weights)))
    aspect_range = composition.get("aspect_ratio", [0.8, 1.8])
    opacity_range = composition.get("opacity", [0.34, 0.68])
    blur_range = composition.get("blur_radius_px", [80.0, 200.0])
    edge_probability = float(composition.get("edge_crop_probability", 0.6))
    flow_bias = str(composition.get("flow_bias", "radial"))
    blob_records: list[dict[str, Any]] = []

    for blob_index, flavor_index in enumerate(assignment):
        relative = float(weights[flavor_index] / max_weight)
        edge_bias = blob_index == 0 or rng.random() < edge_probability
        if flow_bias == "opposing_edges":
            cx = rng.uniform(-0.18, 0.1) if blob_index % 2 == 0 else rng.uniform(0.9, 1.18)
            cy = rng.uniform(0.08, 0.92)
        elif flow_bias == "horizontal":
            cx = rng.uniform(-0.16, 1.16) if edge_bias else rng.uniform(0.08, 0.92)
            cy = (blob_index + 0.6) / (blob_count + 0.2) + rng.uniform(-0.08, 0.08)
        elif flow_bias == "diagonal":
            progress = (blob_index + 0.5) / blob_count
            cx = progress + rng.uniform(-0.28, 0.18)
            cy = 1.0 - progress + rng.uniform(-0.18, 0.28)
        elif flow_bias == "clustered":
            cx = rng.normal(0.52, 0.28)
            cy = rng.normal(0.55, 0.26)
        elif edge_bias:
            side = int(rng.integers(0, 4))
            if side == 0:
                cx, cy = rng.uniform(-0.25, 0.08), rng.uniform(-0.08, 1.08)
            elif side == 1:
                cx, cy = rng.uniform(0.92, 1.25), rng.uniform(-0.08, 1.08)
            elif side == 2:
                cx, cy = rng.uniform(-0.08, 1.08), rng.uniform(-0.22, 0.08)
            else:
                cx, cy = rng.uniform(-0.08, 1.08), rng.uniform(0.92, 1.22)
        else:
            cx, cy = rng.uniform(0.06, 0.94), rng.uniform(0.06, 0.94)

        ratio = rng.uniform(float(aspect_range[0]), float(aspect_range[1]))
        area_scale = (0.72 + 0.34 * relative) * diffusion_scale
        ry = rng.uniform(0.32, 0.58) * area_scale if airy_mesh else rng.uniform(0.2, 0.42) * area_scale
        rx = ry * ratio
        angle = rng.uniform(-math.pi, math.pi)
        if flow_bias == "horizontal":
            angle = rng.uniform(-0.18, 0.18)
        elif flow_bias == "diagonal":
            angle = rng.uniform(-0.95, -0.48)
        falloff = rng.uniform(1.35, 2.15)
        opacity = rng.uniform(float(opacity_range[0]), float(opacity_range[1]))
        opacity *= float(intensity_profile.get("opacity", 1.0))
        field = elliptical_field(Xw, Yw, cx, cy, rx, ry, angle, falloff)
        # Two subordinate lobes break the perfect ellipse into a liquid/cloud-like planar mass.
        for _ in range(2):
            field += elliptical_field(
                Xw,
                Yw,
                cx + rng.uniform(-0.22, 0.22) * rx,
                cy + rng.uniform(-0.2, 0.2) * ry,
                rx * rng.uniform(0.48, 0.78),
                ry * rng.uniform(0.5, 0.82),
                angle + rng.uniform(-0.55, 0.55),
                rng.uniform(1.35, 2.05),
            ) * rng.uniform(0.35, 0.72)
        field *= opacity * (0.78 + 0.42 * relative)
        blur_px = rng.uniform(float(blur_range[0]), float(blur_range[1]))
        blur_px *= float(intensity_profile.get("blur", 1.0))
        if airy_mesh:
            blur_bounds = airy_config.get("field_blur_ratio", [0.18, 0.30])
            blur_px = float(np.clip(blur_px * 1.65, width * float(blur_bounds[0]), width * float(blur_bounds[1])))
        else:
            blur_px = float(np.clip(blur_px, width * 0.10, width * 0.22))
        blur_ratio = blur_px / max(width, 1)
        field = blur_motif_field(field, blur_ratio) * opacity
        fields[flavor_index] += field.astype(np.float32)
        blob_layers.append((field.astype(np.float32), flavor_index, opacity))
        blob_records.append({
            "index": blob_index,
            "flavor_index": flavor_index,
            "center": [round(float(cx), 4), round(float(cy), 4)],
            "radius": [round(float(rx), 4), round(float(ry), 4)],
            "opacity": round(float(opacity), 4),
            "blur_px": round(float(blur_px), 2),
            "edge_cropped": bool(cx - rx < 0 or cx + rx > 1 or cy - ry < 0 or cy + ry > 1),
        })

    stack = np.stack(fields, axis=0)
    # 使用柔和的区域胜出模型：颜色保持扩散，但不会平均成米色或灰色。
    order_bias = np.power(weights / weights.max(), 0.52).astype(np.float32)
    hierarchy_contrast = float(hierarchy_profile.get("contrast_scale", 1.0))
    regional_contrast = np.clip(
        rng.uniform(1.65, 2.25) * contrast_scale * hierarchy_contrast,
        1.15,
        3.2,
    )
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

    srgb_colors = np.stack([hex_to_srgb(item["palette"]["body"]) for item in palette], axis=0)
    oklab_colors = linear_srgb_to_oklab(srgb_to_linear(srgb_colors))
    if airy_mesh:
        highlight_colors = np.stack([
            linear_srgb_to_oklab(srgb_to_linear(hex_to_srgb(item["palette"]["highlight"])))
            for item in palette
        ])
        highlight_mix = float(np.mean(airy_config.get("highlight_mix", [0.38, 0.54])))
        oklab_colors = oklab_colors * (1.0 - highlight_mix) + highlight_colors * highlight_mix
    oklab_colors[:, 1:3] *= float(intensity_profile.get("chroma", 1.0))
    canvas_lab = np.einsum("nhw,nc->hwc", mix_weights, oklab_colors, optimize=True)

    # Reintroduce the three-to-five planned blobs as a true second color-plane layer.
    # This prevents regional normalization from dissolving the artwork back into a gradient.
    hierarchy_opacity = float(hierarchy_profile.get("opacity_scale", 1.0))
    for blob_index, (blob_field, flavor_index, opacity) in enumerate(blob_layers):
        tone = "core" if blob_index % 3 == 0 else "body"
        blob_color = linear_srgb_to_oklab(
            srgb_to_linear(hex_to_srgb(palette[flavor_index]["palette"][tone]))
        )
        blob_color[1:3] *= float(intensity_profile.get("chroma", 1.0))
        if airy_mesh:
            highlight_color = linear_srgb_to_oklab(
                srgb_to_linear(hex_to_srgb(palette[flavor_index]["palette"]["highlight"]))
            )
            body_mix = 0.58 if tone == "body" else 0.74
            blob_color = blob_color * (1.0 - body_mix) + highlight_color * body_mix
        light_shift = 0.035 if blob_index % 2 == 0 else (-0.008 if airy_mesh else -0.025)
        blob_color[0] = np.clip(blob_color[0] + light_shift, 0.2, 0.96)
        if airy_mesh:
            # Normalize each large lobe before compositing; otherwise repeated opacity
            # multiplication makes broad mesh anchors numerically present but invisible.
            normalized_blob = blob_field / max(float(blob_field.max()), 1e-6)
            local_opacity = (0.18 if tone == "core" else 0.30) * (0.82 + 0.28 * float(weights[flavor_index] / max_weight))
            blob_alpha = np.clip(normalized_blob * local_opacity, 0.0, 0.34)[..., None]
        else:
            blob_alpha = np.clip(
                blob_field * opacity * 0.38 * hierarchy_opacity,
                0.0,
                0.28,
            )[..., None]
        canvas_lab = canvas_lab * (1.0 - blob_alpha) + blob_color * blob_alpha

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
    light_alpha = rng.uniform(0.18, 0.32) * light_field[..., None] if airy_mesh else rng.uniform(0.08, 0.22) * light_field[..., None]
    highlight_index = int(np.argmax(weights))
    warm_light = linear_srgb_to_oklab(
        srgb_to_linear(hex_to_srgb(palette[highlight_index]["palette"]["highlight"]))
    )
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
    anchor_color[0] = max(0.56 if airy_mesh else 0.22, anchor_color[0] - rng.uniform(0.015 if airy_mesh else 0.05, 0.055 if airy_mesh else 0.14))
    anchor_alpha = rng.uniform(0.04, 0.10) * anchor_field[..., None] if airy_mesh else rng.uniform(0.05, 0.17) * anchor_field[..., None]
    canvas_lab = canvas_lab * (1.0 - anchor_alpha) + anchor_color * anchor_alpha

    # 只叠加一个主母题和一个互补辅助母题；形态保持超大、裁切、柔边与半透明。
    motif_diagnostics: list[dict[str, Any]] = []
    if not airy_mesh and selected_motifs:
        canvas_lab, motif_diagnostics = apply_flavor_motifs(
            canvas_lab, Xw, Yw, oklab_colors, selected_motifs, processing_renderer,
            motif_visibility, rng
        )

    # 使用低频明度调制增强氛围纵深。
    canvas_lab[..., 0] += np.clip(luminance_noise, -2.0, 2.0) * rng.uniform(0.004, 0.014)

    # 防止跨色相混合后色度塌陷成灰褐色，同时保持混合后的色相与深色锚点。
    canvas_lab = protect_color_clarity(canvas_lab, mix_weights, oklab_colors)

    breathing_area_ratio = 0.0
    breathing_center_strength = 0.0
    airy_plane_records: list[dict[str, Any]] = []
    if airy_mesh:
        # Airy mesh uses flavor-derived highlights as the atmosphere; no unrelated white hue is injected.
        source_highlights = np.stack([
            linear_srgb_to_oklab(srgb_to_linear(hex_to_srgb(item["palette"]["highlight"])))
            for item in palette
        ])
        breathing_color = np.sum(source_highlights * weights[:, None], axis=0)
        breathing_color[0] = float(np.clip(breathing_color[0] + 0.075, 0.89, 0.95))
        breathing_color[1:3] *= 0.28
        base_mix = float(np.mean(airy_config.get("base_highlight_blend", [0.26, 0.38])))
        canvas_lab = canvas_lab * (1.0 - base_mix) + breathing_color * base_mix

        # Establish a few readable edge-entering color planes. They are deliberately
        # oversized and cropped, so the result reads as one mesh rather than colored dots.
        edge_positions = [
            (-0.12, 0.22), (0.98, 0.16), (-0.10, 0.86), (1.06, 0.78)
        ]
        position_shift = int(rng.integers(0, len(edge_positions)))
        for field_index in range(min(len(palette), 4)):
            cx, cy = edge_positions[(field_index + position_shift) % len(edge_positions)]
            cx += rng.uniform(-0.08, 0.08)
            cy += rng.uniform(-0.08, 0.08)
            plane = elliptical_field(
                Xw, Yw, cx, cy,
                rng.uniform(0.42, 0.68), rng.uniform(0.36, 0.62),
                rng.uniform(-1.2, 1.2), rng.uniform(1.25, 1.8),
            )
            plane += 0.55 * elliptical_field(
                Xw, Yw,
                cx + rng.uniform(-0.10, 0.10), cy + rng.uniform(-0.10, 0.10),
                rng.uniform(0.24, 0.42), rng.uniform(0.26, 0.46),
                rng.uniform(-1.4, 1.4), rng.uniform(1.25, 1.9),
            )
            plane = blur_motif_field(plane, rng.uniform(0.11, 0.17))
            plane /= max(float(plane.max()), 1e-6)
            body_color = linear_srgb_to_oklab(
                srgb_to_linear(hex_to_srgb(palette[field_index]["palette"]["body"]))
            )
            highlight_color = source_highlights[field_index]
            plane_color = body_color * 0.82 + highlight_color * 0.18
            relative_weight = float(weights[field_index] / max_weight)
            plane_strength = 0.44 + 0.28 * math.sqrt(relative_weight)
            plane_alpha = np.clip(plane * plane_strength, 0.0, 0.74)[..., None]
            canvas_lab = canvas_lab * (1.0 - plane_alpha) + plane_color * plane_alpha
            airy_plane_records.append({
                "field_index": field_index,
                "center": [round(float(cx), 4), round(float(cy), 4)],
                "peak_opacity": round(float(plane_strength), 4),
                "edge_entering": True,
            })

        breathing = elliptical_field(
            Xw, Yw,
            rng.uniform(0.34, 0.68), rng.uniform(0.34, 0.72),
            rng.uniform(0.30, 0.48), rng.uniform(0.24, 0.40),
            rng.uniform(-1.15, 1.15), rng.uniform(1.25, 1.75),
        )
        breathing = blur_motif_field(breathing, rng.uniform(0.12, 0.18))
        breathing_alpha = np.clip(breathing * rng.uniform(0.38, 0.54), 0.0, 0.56)[..., None]
        canvas_lab = canvas_lab * (1.0 - breathing_alpha) + breathing_color * breathing_alpha
        breathing_area_ratio = float(np.mean(breathing > 0.58))
        breathing_center_strength = float(breathing[work_height // 2, work_width // 2])
        canvas_lab[..., 0] = np.clip(canvas_lab[..., 0], 0.60, 0.94)
        canvas_lab[..., 1:3] *= 0.92
        # Semantic forms sit inside the airy field, after the atmosphere is established,
        # so floral contours remain discoverable instead of being washed away.
        if selected_motifs:
            canvas_lab, motif_diagnostics = apply_flavor_motifs(
                canvas_lab, Xw, Yw, oklab_colors, selected_motifs, processing_renderer,
                motif_visibility, rng
            )

    linear_rgb = oklab_to_linear_srgb(canvas_lab)
    srgb = np.clip(linear_to_srgb(linear_rgb), 0.0, 1.0)
    image = Image.fromarray(np.uint8(srgb * 255.0), mode="RGB")
    image = image.resize((width, height), Image.Resampling.LANCZOS)

    # 在最终分辨率下添加细腻的哑光颗粒。
    full = np.asarray(image, dtype=np.float32) / 255.0
    grain_rng = np.random.default_rng(composition_seed ^ 0xA5A5A5A5)
    mono = grain_rng.normal(0.0, 1.0, (height, width, 1)).astype(np.float32)
    colored = grain_rng.normal(0.0, 1.0, (height, width, 3)).astype(np.float32)
    if airy_mesh:
        grain_bounds = airy_config.get("grain_opacity", [0.012, 0.022])
        effective_grain = float(np.clip(grain_strength * grain_scale, float(grain_bounds[0]), float(grain_bounds[1])))
    else:
        effective_grain = grain_strength * grain_scale
    texture = mono * effective_grain * 0.70 + colored * effective_grain * 0.16
    # 中间调颗粒稍强，高光和深阴影区域更安静。
    luma = full.mean(axis=2, keepdims=True)
    midtone_mask = 0.60 + 0.40 * (1.0 - np.abs(luma - 0.5) * 1.5)
    full = np.clip(full + texture * midtone_mask, 0.0, 1.0)

    if texture_mode == "glass_diffusion":
        diffused = np.asarray(
            Image.fromarray(np.uint8(full * 255.0), mode="RGB").filter(
                ImageFilter.GaussianBlur(max(1.0, width * 0.0024))
            ),
            dtype=np.float32,
        ) / 255.0
        full = np.clip(full * 0.72 + diffused * 0.28 + 0.008, 0.0, 1.0)
    elif texture_mode == "liquid_glow":
        blurred = np.asarray(
            Image.fromarray(np.uint8(full * 255.0), mode="RGB").filter(
                ImageFilter.GaussianBlur(max(2.0, width * 0.012))
            ),
            dtype=np.float32,
        ) / 255.0
        glow = np.maximum(blurred - 0.48, 0.0) * 0.12
        full = np.clip(full + glow, 0.0, 1.0)
    elif texture_mode == "spray_particle":
        particle_mask = grain_rng.random((height, width)) < 0.0015
        if np.any(particle_mask):
            particle_palette = np.stack([hex_to_srgb(item["hex"]) for item in palette])
            particle_indexes = grain_rng.integers(0, len(particle_palette), size=int(particle_mask.sum()))
            particle_alpha = grain_rng.uniform(0.18, 0.42, size=(int(particle_mask.sum()), 1))
            full[particle_mask] = (
                full[particle_mask] * (1.0 - particle_alpha)
                + particle_palette[particle_indexes] * particle_alpha
            )

    # 叠加统一的材质层：细噪点、纸张纤维与稀疏咖啡粉颗粒。
    material_opacity = float(composition.get("texture_opacity", 0.12))
    material_opacity *= float(hierarchy_profile.get("texture_scale", 1.0))
    material_opacity = float(np.clip(material_opacity, 0.04 if airy_mesh else 0.06, 0.09 if airy_mesh else 0.2))
    fiber_small = grain_rng.normal(
        0.0, 1.0, (max(8, height // 44), max(8, width // 11))
    ).astype(np.float32)
    fiber_low, fiber_high = float(fiber_small.min()), float(fiber_small.max())
    fiber_small = (fiber_small - fiber_low) / max(fiber_high - fiber_low, 1e-6)
    fiber_image = Image.fromarray(np.uint8(fiber_small * 255.0), mode="L")
    fiber_image = fiber_image.resize((width, height), Image.Resampling.BICUBIC)
    fiber_image = fiber_image.filter(ImageFilter.GaussianBlur(max(0.8, width * 0.0012)))
    fiber = np.asarray(fiber_image, dtype=np.float32) / 255.0 - 0.5
    full = np.clip(full + fiber[..., None] * (0.035 * material_opacity), 0.0, 1.0)
    powder_probability = 0.00035 * float(hierarchy_profile.get("texture_scale", 1.0))
    powder_mask = grain_rng.random((height, width)) < powder_probability
    if np.any(powder_mask):
        powder_alpha = grain_rng.uniform(0.035, 0.12, size=(int(powder_mask.sum()), 1))
        powder_tone = np.clip(full[powder_mask] * 0.58, 0.0, 1.0)
        full[powder_mask] = full[powder_mask] * (1.0 - powder_alpha) + powder_tone * powder_alpha

    composition_diagnostics = {
        "gradient_style": gradient_style,
        "style": composition.get("key"),
        "label": composition.get("label"),
        "visual_language": composition.get("visual_language"),
        "organic_blob_count": len(blob_records),
        "organic_blobs": blob_records,
        "field_area_soft": [round(float(value), 6) for value in mix_weights.mean(axis=(1, 2))],
        "field_area_dominant": [
            round(float(np.mean(np.argmax(mix_weights, axis=0) == index)), 6)
            for index in range(len(palette))
        ],
        "minimum_transition_width_ratio": round(
            min(record["blur_px"] for record in blob_records) / max(width, 1), 6
        ),
        "breathing_area_ratio": round(breathing_area_ratio, 6),
        "breathing_center_strength": round(breathing_center_strength, 6),
        "airy_edge_planes": airy_plane_records,
        "material_texture": {
            "opacity": round(material_opacity, 4),
            "layers": ["fine_noise", "paper_fiber", "coffee_powder_particles"],
            "processing_mode": texture_mode,
        },
    }
    return (
        Image.fromarray(np.uint8(full * 255.0), mode="RGB"),
        motif_diagnostics,
        composition_diagnostics,
    )


QUALITY_RULES = {
    "max_primary_fields": 4,
    "max_secondary_shapes": 0,
    "max_hard_edge_ratio": 0.03,
    "minimum_primary_flavor_area": 0.38,
    "maximum_fragment_count": 6,
    "minimum_transition_width_ratio": 0.10,
    "maximum_dark_area_ratio": 0.18,
    "minimum_color_coherence_score": 0.75,
    "minimum_flavor_fidelity_score": 0.80,
    "minimum_semantic_contour_score": 0.75,
}

AIRY_MESH_QUALITY_RULES = {
    "minimum_median_luma": 0.68,
    "maximum_median_luma": 0.86,
    "minimum_high_key_ratio": 0.04,
    "maximum_high_key_ratio": 0.76,
    "minimum_breathing_area_ratio": 0.16,
    "maximum_breathing_area_ratio": 0.42,
    "minimum_breathing_center_strength": 0.35,
    "minimum_median_saturation": 0.10,
    "maximum_median_saturation": 0.38,
    "maximum_low_frequency_gradient_p95": 0.035,
}


def evaluate_quality(
    image: Image.Image,
    fields: list[dict[str, Any]],
    composition_diagnostics: dict[str, Any],
    motif_diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Measure the 2.0 guardrails on the background before typography is added."""
    sample = np.asarray(image.resize((270, 360), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
    luma = sample[..., 0] * 0.2126 + sample[..., 1] * 0.7152 + sample[..., 2] * 0.0722
    gy, gx = np.gradient(luma)
    gradient = np.sqrt(gx * gx + gy * gy)
    hard_edge_ratio = float(np.mean(gradient > 0.11))
    dark_area_ratio = float(np.mean(luma < 0.12))
    channel_spread = sample.max(axis=2) - sample.min(axis=2)
    saturation = channel_spread / np.maximum(sample.max(axis=2), 1e-6)
    gray_ratio = float(np.mean((channel_spread < 0.055) & (luma < 0.9)))
    color_coherence_score = float(np.clip(1.0 - gray_ratio * 0.9 - hard_edge_ratio * 1.8, 0.0, 1.0))
    soft_areas = composition_diagnostics.get("field_area_soft", [])
    primary_area = float(soft_areas[0]) if soft_areas else 0.0
    primary_source_weight = float(sum(
        DEFAULT_FLAVOR_WEIGHTS[index]
        for index in fields[0].get("member_indexes", [0])
        if index < len(DEFAULT_FLAVOR_WEIGHTS)
    ))
    primary_source_weight /= float(DEFAULT_FLAVOR_WEIGHTS[:sum(len(f.get("member_indexes", [])) for f in fields)].sum())
    fidelity = float(np.clip(
        0.55
        + min(primary_area / max(primary_source_weight, 1e-6), 1.0) * 0.25
        + color_coherence_score * 0.20,
        0.0,
        1.0,
    ))
    fragment_count = int(composition_diagnostics.get("organic_blob_count", 0))
    transition_ratio = float(composition_diagnostics.get("minimum_transition_width_ratio", 0.0))
    required_contours = [
        item.get("contour", {})
        for item in motif_diagnostics
        if item.get("contour", {}).get("required")
    ]
    semantic_contour_score = min(
        (float(item.get("semantic_contour_score", 0.0)) for item in required_contours),
        default=1.0,
    )
    metrics = {
        "primary_field_count": len(fields),
        "secondary_shape_count": max(0, len(motif_diagnostics) - 1),
        "hard_edge_ratio": round(hard_edge_ratio, 6),
        "primary_flavor_area": round(primary_area, 6),
        "fragment_count": fragment_count,
        "minimum_transition_width_ratio": round(transition_ratio, 6),
        "dark_area_ratio": round(dark_area_ratio, 6),
        "color_coherence_score": round(color_coherence_score, 6),
        "flavor_fidelity_score": round(fidelity, 6),
        "semantic_contour_score": round(semantic_contour_score, 6),
        "median_luma": round(float(np.median(luma)), 6),
        "high_key_ratio": round(float(np.mean(luma > 0.78)), 6),
        "median_saturation": round(float(np.median(saturation)), 6),
        "low_frequency_gradient_p95": round(float(np.quantile(gradient, 0.95)), 6),
        "breathing_area_ratio": round(float(composition_diagnostics.get("breathing_area_ratio", 0.0)), 6),
        "breathing_center_strength": round(float(composition_diagnostics.get("breathing_center_strength", 0.0)), 6),
    }
    failures: list[str] = []
    comparisons = (
        (len(fields) <= QUALITY_RULES["max_primary_fields"], "primary_fields"),
        (metrics["secondary_shape_count"] <= QUALITY_RULES["max_secondary_shapes"], "secondary_shapes"),
        (hard_edge_ratio <= QUALITY_RULES["max_hard_edge_ratio"], "hard_edges"),
        (primary_area >= QUALITY_RULES["minimum_primary_flavor_area"], "primary_area"),
        (fragment_count <= QUALITY_RULES["maximum_fragment_count"], "fragments"),
        (transition_ratio >= QUALITY_RULES["minimum_transition_width_ratio"], "transition_width"),
        (dark_area_ratio <= QUALITY_RULES["maximum_dark_area_ratio"], "dark_area"),
        (color_coherence_score >= QUALITY_RULES["minimum_color_coherence_score"], "color_coherence"),
        (fidelity >= QUALITY_RULES["minimum_flavor_fidelity_score"], "flavor_fidelity"),
        (
            semantic_contour_score >= QUALITY_RULES["minimum_semantic_contour_score"],
            "semantic_contour",
        ),
    )
    failures.extend(label for passed, label in comparisons if not passed)
    if composition_diagnostics.get("gradient_style") == "airy_mesh":
        airy_comparisons = (
            (metrics["median_luma"] >= AIRY_MESH_QUALITY_RULES["minimum_median_luma"], "airy_median_luma_low"),
            (metrics["median_luma"] <= AIRY_MESH_QUALITY_RULES["maximum_median_luma"], "airy_median_luma_high"),
            (metrics["high_key_ratio"] >= AIRY_MESH_QUALITY_RULES["minimum_high_key_ratio"], "airy_high_key_area"),
            (metrics["high_key_ratio"] <= AIRY_MESH_QUALITY_RULES["maximum_high_key_ratio"], "airy_high_key_area_excess"),
            (metrics["breathing_area_ratio"] >= AIRY_MESH_QUALITY_RULES["minimum_breathing_area_ratio"], "airy_breathing_area"),
            (metrics["breathing_area_ratio"] <= AIRY_MESH_QUALITY_RULES["maximum_breathing_area_ratio"], "airy_breathing_area_excess"),
            (metrics["breathing_center_strength"] >= AIRY_MESH_QUALITY_RULES["minimum_breathing_center_strength"], "airy_breathing_center"),
            (metrics["median_saturation"] >= AIRY_MESH_QUALITY_RULES["minimum_median_saturation"], "airy_saturation_low"),
            (metrics["median_saturation"] <= AIRY_MESH_QUALITY_RULES["maximum_median_saturation"], "airy_saturation_high"),
            (metrics["low_frequency_gradient_p95"] <= AIRY_MESH_QUALITY_RULES["maximum_low_frequency_gradient_p95"], "airy_transition_smoothness"),
        )
        failures.extend(label for passed, label in airy_comparisons if not passed)
    return {
        "passed": not failures,
        "rules": {
            **QUALITY_RULES,
            **(AIRY_MESH_QUALITY_RULES if composition_diagnostics.get("gradient_style") == "airy_mesh" else {}),
        },
        "metrics": metrics,
        "failures": failures,
    }


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
        processing_data = load_json(PROCESSING_PATH)
        origin_data = load_json(ORIGIN_PATH)
        semantic_data = load_json(SEMANTIC_PATH)
        composition_data = load_json(COMPOSITION_PATH)
        processing_key, processing, processing_source = detect_profile(
            args.processing_method,
            args.coffee_name,
            processing_data["processing_system"],
            processing_data.get("fallback", "neutral"),
            processing_data.get("detection_order"),
        )
        origin_key, origin, origin_source = detect_profile(
            args.origin,
            args.coffee_name,
            origin_data["origin_adjustments"],
            origin_data.get("fallback", "neutral"),
        )
        base_palette = resolve_palette(flavors, data, overrides)
        weights = compute_weights(len(flavors), args.decay)
        semantic_palette = enrich_semantic_palette(base_palette, semantic_data)
        palette, field_weights, flavor_to_field = cluster_semantic_fields(
            semantic_palette, weights
        )
        # The current visual direction is a pure continuous gradient field.
        # Keep semantic categories for palette resolution, but never render
        # petals, rings, ribbons, blobs, contours, or other graphic motifs.
        selected_motifs: list[dict[str, Any]] = []
        requested_seed = args.seed if args.seed is not None else secrets.randbits(32)
        flavor_hierarchy = resolve_flavor_hierarchy(
            flavors, base_palette, weights, composition_data
        )
        if args.template_style == "info_panel":
            if not args.country or not args.country.strip():
                raise ValueError("info_panel 模版必须提供 --country")
            if not args.processing_method:
                raise ValueError("info_panel 模版必须提供 --processing-method")
            template_font_path = Path(args.template_font).expanduser() if args.template_font else BUNDLED_TEMPLATE_FONT
            # Validate the exact regular and bold faces before starting the render.
            if args.language == "zh":
                load_chinese_panel_font(32, 400)
                load_chinese_panel_font(32, 700)
            else:
                load_info_panel_font(template_font_path, 32, 400)
                load_info_panel_font(template_font_path, 32, 700)
            coffee_font_path = flavor_font_path = None
        else:
            template_font_path = None
            coffee_font_path = resolve_required_font(args.language, "coffee", args.coffee_font)
            flavor_font_path = resolve_required_font(args.language, "flavor", args.flavor_font)

        output = Path(args.output).expanduser().resolve()
        if output.suffix.lower() != ".png":
            output = output.with_suffix(".png")
        output.parent.mkdir(parents=True, exist_ok=True)

        intensity_profile = INTENSITY_PROFILES[args.visual_intensity]
        gradient_style_config = semantic_data.get("gradient_styles", {}).get(args.gradient_style, {})
        safe_texture_mode = {
            "washed": "glass_diffusion",
            "honey": "liquid_glow",
        }.get(processing_key, "matte_grain")
        mood_renderer = {
            "warp_scale": float(np.clip(processing.get("renderer", {}).get("warp_scale", 1.0), 0.9, 1.1)),
            "diffusion_scale": float(np.clip(processing.get("renderer", {}).get("diffusion_scale", 1.0), 0.92, 1.08)),
            "texture_mode": safe_texture_mode,
        }
        audits: list[dict[str, Any]] = []
        image = None
        motif_diagnostics: list[dict[str, Any]] = []
        composition_diagnostics: dict[str, Any] = {}
        composition: dict[str, Any] = {}
        composition_seed = requested_seed
        maximum_attempts = int(np.clip(args.max_quality_attempts, 1, 8))
        for attempt in range(maximum_attempts):
            composition_seed = (requested_seed + attempt * 0x9E3779B1) & 0xFFFFFFFF
            composition = select_composition(
                "neutral", palette, field_weights, flavor_hierarchy,
                composition_data, composition_seed,
            )
            candidate, candidate_motifs, candidate_composition = render(
                palette=palette,
                weights=field_weights,
                width=args.width,
                height=args.height,
                composition_seed=composition_seed,
                grain_strength=float(np.clip(args.grain, 0.015, 0.045)),
                processing_renderer=mood_renderer,
                selected_motifs=selected_motifs,
                motif_visibility=semantic_data.get("visibility", {}),
                composition=composition,
                intensity_profile=intensity_profile,
                gradient_style=args.gradient_style,
                gradient_style_config=gradient_style_config,
            )
            audit = evaluate_quality(
                candidate, palette, candidate_composition, candidate_motifs
            )
            audits.append({"attempt": attempt + 1, "seed": composition_seed, **audit})
            if audit["passed"]:
                image = candidate
                motif_diagnostics = candidate_motifs
                composition_diagnostics = candidate_composition
                break
        if image is None:
            raise ValueError(f"自动质检连续 {maximum_attempts} 次未通过：{audits}")
        if args.template_style == "info_panel":
            typography = add_info_panel_typography(
                image, args.coffee_name, display_flavors, args.language,
                args.country, processing_key, args.processing_label,
                args.processing_icon, template_font_path,
            )
        else:
            typography = add_typography(
                image,
                args.coffee_name,
                display_flavors,
                args.language,
                coffee_font_path,
                flavor_font_path,
            )
        image.save(output, format="PNG", optimize=args.optimize_png)

        palette_key_text = "|".join(item["normalized"] for item in semantic_palette)
        metadata = {
            "version": "2.0.0",
            "system_name": "Flavor Semantic Color Field",
            "highest_principle": semantic_data.get("highest_principle"),
            "palette_version": data.get("paletteVersion", "unknown"),
            "dimensions": {"width": args.width, "height": args.height, "ratio": "3:4"},
            "palette_key": hashlib.sha256(palette_key_text.encode("utf-8")).hexdigest()[:16],
            "requested_seed": requested_seed,
            "composition_seed": composition_seed,
            "visual_intensity": args.visual_intensity,
            "gradient_style": args.gradient_style,
            "template_style": args.template_style,
            "floral_treatment": "disabled",
            "default_weight_model": [0.42, 0.25, 0.16, 0.10, 0.07],
            "grain": args.grain,
            "flavor_semantic_color_field": {
                "flavor_is_only_hue_source": True,
                "processing": {
                    "key": processing_key,
                    "source": processing_source,
                    "role": "restrained global mood only; never a hue source",
                    "renderer": mood_renderer,
                },
                "origin": {
                    "key": origin_key,
                    "source": origin_source,
                    "role": "metadata only; no hue injection",
                },
                "semantic_shapes": {
                    "enabled": False,
                    "policy": "pure_continuous_gradient_only",
                    "selected": [],
                    "visibility_diagnostics": [],
                },
                "color_clusters": [
                    {
                        "cluster_index": item["cluster_index"],
                        "category": item["category"],
                        "members": item["member_flavors"],
                        "member_indexes": item["member_indexes"],
                        "weight": round(float(field_weights[index]), 6),
                        "palette": item["palette"],
                        "shape_language": item["shape_language"],
                    }
                    for index, item in enumerate(palette)
                ],
                "composition": {
                    "selection": composition,
                    "rendered": composition_diagnostics,
                },
                "gradient_style": {
                    "key": args.gradient_style,
                    "parameters": gradient_style_config,
                },
            },
            "color_cleaning": {
                "enabled": True,
                "minimum_chroma_ratio": 0.68,
                "minimum_source_chroma": 0.045,
                "maximum_target_chroma": 0.16,
            },
            "typography": typography,
            "flavors": [
                {**item, "weight": round(float(weights[i]), 6)}
                for i, item in enumerate(semantic_palette)
            ],
            "quality_control": {
                "passed": True,
                "attempt_count": len(audits),
                "attempts": audits,
            },
            "output": str(output),
        }
        metadata_path = output.with_suffix(".json")
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps({
            "png": str(output),
            "metadata": str(metadata_path),
            "seed": composition_seed,
            "visual_intensity": args.visual_intensity,
            "gradient_style": args.gradient_style,
            "floral_treatment": "disabled",
            "primary_fields": len(palette),
            "quality_attempts": len(audits),
            "composition_style": composition.get("key"),
        }, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

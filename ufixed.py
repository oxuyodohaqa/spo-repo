#!/usr/bin/env python3
"""Render student ID cards on the shared template with consistent layout.

This renderer keeps the same layout for every country. It overlays the
college name, student name, and supporting details onto the shared
``mentahan.jpg`` template while allowing callers to swap country labels
without altering the design.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent / "mentahan.jpg"
DEFAULT_OUTPUT_DIR = Path("receipts")
COUNTRY_PRESETS_PATH = Path(__file__).parent / "countries.json"

# Default presets in case the JSON file is missing or invalid.
DEFAULT_COUNTRY_PRESETS = [
    {"name": "Indonesia", "flag": "🇮🇩", "college": "Universitas Islam Indonesia"},
    {"name": "Malaysia", "flag": "🇲🇾", "college": "Universiti Malaya"},
    {"name": "Singapore", "flag": "🇸🇬", "college": "National University of Singapore"},
    {"name": "India", "flag": "🇮🇳", "college": "Indian Institute of Technology"},
    {"name": "Philippines", "flag": "🇵🇭", "college": "University of the Philippines"},
    {"name": "Thailand", "flag": "🇹🇭", "college": "Chulalongkorn University"},
    {"name": "Vietnam", "flag": "🇻🇳", "college": "Vietnam National University"},
    {"name": "Brunei", "flag": "🇧🇳", "college": "Universiti Brunei Darussalam"},
    {"name": "Pakistan", "flag": "🇵🇰", "college": "University of the Punjab"},
    {"name": "Bangladesh", "flag": "🇧🇩", "college": "University of Dhaka"},
    {"name": "Sri Lanka", "flag": "🇱🇰", "college": "University of Colombo"},
    {"name": "Nepal", "flag": "🇳🇵", "college": "Tribhuvan University"},
    {"name": "Myanmar", "flag": "🇲🇲", "college": "University of Yangon"},
    {"name": "Cambodia", "flag": "🇰🇭", "college": "Royal University of Phnom Penh"},
    {"name": "Laos", "flag": "🇱🇦", "college": "National University of Laos"},
    {"name": "China", "flag": "🇨🇳", "college": "Tsinghua University"},
    {"name": "Japan", "flag": "🇯🇵", "college": "University of Tokyo"},
    {"name": "South Korea", "flag": "🇰🇷", "college": "Seoul National University"},
    {"name": "United States", "flag": "🇺🇸", "college": "Massachusetts Institute of Technology"},
    {"name": "United Kingdom", "flag": "🇬🇧", "college": "University of Oxford"},
]


@dataclass
class CardData:
    college_name: str
    student_name: str
    class_name: str
    phone: str
    ttl: str
    student_id: str
    address: str
    admission_period: str
    country: str
    country_flag: str
    contact_info: str
    alias: str | None = None
    photo_path: Path | None = None

    @property
    def display_alias(self) -> str:
        """Return a secondary name line if available."""
        return self.alias or ""

    @property
    def country_line(self) -> str:
        return f"{self.country_flag} {self.country}".strip()


def load_college_file(path: Path) -> List[str]:
    """Return a list of college names from an external JSON file."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # Support both simple string lists and lists of objects with a
            # "name" field, which matches the provided college data format.
            names = []
            for item in data:
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))
                elif isinstance(item, str):
                    names.append(item)
            return [name for name in names if str(name).strip()]
        logger.warning("College file %s is not a list; skipping", path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read college file %s: %s", path, exc)
    return []


def load_country_presets() -> Dict[str, Dict[str, object]]:
    """Load country presets from JSON, falling back to the built-in list.

    Supports optional "collegeFile" entries to load a full college list per country.
    """

    def build_lookup(entries: List[dict]) -> Dict[str, Dict[str, object]]:
        lookup: Dict[str, Dict[str, object]] = {}
        for entry in entries:
            name = entry.get("name")
            if not name:
                continue
            flag = entry.get("flag", "")
            college = entry.get("college", "")
            college_file = entry.get("collegeFile")
            colleges: List[str] = []
            if college_file:
                path = COUNTRY_PRESETS_PATH.parent / college_file
                colleges = load_college_file(path)
            if college and not colleges:
                colleges = [college]
            lookup[name.lower()] = {
                "flag": flag,
                "college": colleges[0] if colleges else college,
                "colleges": colleges,
                "college_file": college_file,
            }
        return lookup

    if COUNTRY_PRESETS_PATH.exists():
        try:
            presets = json.loads(COUNTRY_PRESETS_PATH.read_text(encoding="utf-8"))
            if isinstance(presets, list):
                lookup = build_lookup(presets)
                if lookup:
                    return lookup
            logger.warning("Country presets JSON malformed; using defaults")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read %s: %s; using defaults", COUNTRY_PRESETS_PATH, exc)

    return build_lookup(DEFAULT_COUNTRY_PRESETS)


def load_fonts() -> Dict[str, ImageFont.FreeTypeFont]:
    """Load a set of fonts for the card.

    Uses Playfair if available; otherwise falls back to Pillow defaults.
    """
    playfair = Path(__file__).parent / "PlayfairDisplay-VariableFont_wght.ttf"
    if playfair.exists():
        return {
            "college": ImageFont.truetype(str(playfair), 56),
            "name": ImageFont.truetype(str(playfair), 60),
            "alias": ImageFont.truetype(str(playfair), 40),
            "label": ImageFont.truetype(str(playfair), 34),
            "body": ImageFont.truetype(str(playfair), 30),
            "small": ImageFont.truetype(str(playfair), 26),
        }

    default = ImageFont.load_default()
    return {key: default for key in ["college", "name", "alias", "label", "body", "small"]}


def draw_centered(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, x: float, y: float, fill: str) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (bbox[2] - bbox[0]) / 2, y - (bbox[3] - bbox[1]) / 2), text, font=font, fill=fill)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    words = text.split()
    lines = []
    current = []
    for word in words:
        trial = " ".join(current + [word])
        width = draw.textlength(trial, font=font)
        if width <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def resolve_country_inputs(
    country: str, country_flag: str | None, presets: Dict[str, Dict[str, object]]
) -> Tuple[str, str, str, List[str]]:
    """Return a normalized country name and flag.

    The layout stays the same for every country; this helper simply keeps
    the previous country list available so callers can skip typing flags.
    """

    normalized = country.strip()
    preset = presets.get(normalized.lower())

    if country_flag:
        colleges = preset.get("colleges", []) if preset else []
        preset_college = preset.get("college") if preset else ""
        return normalized, country_flag, preset_college, colleges

    if preset:
        return (
            normalized,
            preset.get("flag", ""),
            preset.get("college", ""),
            preset.get("colleges", []),
        )

    logger.warning("No preset flag found for %s; leaving flag blank", normalized)
    return normalized, "", "", []


def paste_photo(base: Image.Image, draw: ImageDraw.ImageDraw, data: CardData, area: Tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = area
    if data.photo_path and data.photo_path.exists():
        try:
            photo = Image.open(data.photo_path).convert("RGB")
            photo_ratio = photo.width / photo.height
            target_ratio = (x1 - x0) / (y1 - y0)
            if photo_ratio > target_ratio:
                new_height = y1 - y0
                new_width = int(new_height * photo_ratio)
            else:
                new_width = x1 - x0
                new_height = int(new_width / photo_ratio)
            photo = photo.resize((new_width, new_height))
            offset_x = x0 + ((x1 - x0) - new_width) // 2
            offset_y = y0 + ((y1 - y0) - new_height) // 2
            base.paste(photo, (offset_x, offset_y))
            return
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load photo %s: %s", data.photo_path, exc)

    # Placeholder if no photo available
    draw.rectangle(area, fill="#e5e7eb", outline="#cbd5e1", width=4)
    placeholder_text = "Photo"
    photo_font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), placeholder_text, font=photo_font)
    draw.text(
        (x0 + ((x1 - x0) - (bbox[2] - bbox[0])) / 2, y0 + ((y1 - y0) - (bbox[3] - bbox[1])) / 2),
        placeholder_text,
        font=photo_font,
        fill="#475569",
    )


def render_card(data: CardData, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        base = Image.open(TEMPLATE_PATH).convert("RGB")
    except FileNotFoundError:
        logger.warning("Template %s not found, using plain background", TEMPLATE_PATH)
        base = Image.new("RGB", (1600, 900), "white")

    draw = ImageDraw.Draw(base)
    fonts = load_fonts()
    width, height = base.size

    # Top college name
    draw_centered(draw, data.college_name, fonts["college"], width / 2, height * 0.08, "#1e3a8a")

    # Main name block on the right half
    right_x = width * 0.58
    name_y = height * 0.25
    draw_centered(draw, data.student_name, fonts["name"], right_x, name_y, "#111827")
    if data.display_alias:
        draw_centered(draw, data.display_alias, fonts["alias"], right_x, name_y + 60, "#334155")

    # Details on the right column
    detail_start_y = name_y + 120
    line_gap = 46
    labels = [
        ("Class", data.class_name),
        ("Phone", data.phone),
        ("TTL", data.ttl),
        ("Student ID", data.student_id),
        ("Address", data.address),
    ]
    max_body_width = int(width * 0.32)
    y = detail_start_y
    for label, value in labels:
        label_text = f"{label}" if label.endswith(":") else f"{label}"
        draw.text((right_x - max_body_width / 2, y), label_text, font=fonts["label"], fill="#2563eb")
        wrapped = wrap_text(draw, value, fonts["body"], max_body_width)
        draw.text((right_x - max_body_width / 2, y + 30), wrapped, font=fonts["body"], fill="#111827")
        y += line_gap + 20 * wrapped.count("\n")

    # Left column: country and since lines near the bottom of the photo area
    photo_area = (
        int(width * 0.08),
        int(height * 0.2),
        int(width * 0.38),
        int(height * 0.68),
    )
    paste_photo(base, draw, data, photo_area)

    info_y = photo_area[3] + 20
    draw.text((photo_area[0], info_y), f"Student ID {data.student_id}", font=fonts["small"], fill="#111827")
    draw.text((photo_area[0], info_y + 32), f"Country: {data.country_line}", font=fonts["small"], fill="#111827")
    draw.text((photo_area[0], info_y + 64), f"Student Since {data.admission_period}", font=fonts["small"], fill="#111827")

    # Footer contact info
    footer_y = height * 0.9
    contact_text = data.contact_info
    contact_box_width = draw.textlength(contact_text, font=fonts["small"]) + 40
    contact_x = (width - contact_box_width) / 2
    draw.rectangle(
        [contact_x - 10, footer_y - 16, contact_x + contact_box_width + 10, footer_y + 20],
        fill="white",
        outline="#2563eb",
        width=2,
    )
    draw.text((contact_x, footer_y), contact_text, font=fonts["small"], fill="#111827")

    output_path = output_path.with_suffix(".png")
    base.save(output_path, "PNG", quality=95, optimize=True)
    logger.info("Saved ID card to %s", output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render an ID card with a consistent layout for any country.")
    parser.add_argument("college_name", nargs="?", help="College name to display at the top (uses preset if omitted)")
    parser.add_argument("student_name", nargs="?", help="Primary student name")
    parser.add_argument("class_name", nargs="?", help="Class or major")
    parser.add_argument("phone", nargs="?", help="Phone number")
    parser.add_argument("ttl", nargs="?", help="Birth details (TTL)")
    parser.add_argument("student_id", nargs="?", help="Student ID")
    parser.add_argument("address", nargs="?", help="Address block")
    parser.add_argument("admission_period", nargs="?", help="Admission period label")
    parser.add_argument("country", nargs="?", help="Country name")
    parser.add_argument(
        "--country-flag",
        dest="country_flag",
        help="Country flag emoji or shorthand (auto-filled for common countries)",
    )
    parser.add_argument("contact_info", help="Footer contact info")
    parser.add_argument("--alias", help="Secondary name line", default=None)
    parser.add_argument("--photo", type=Path, help="Path to a photo to place on the card")
    parser.add_argument("--list-countries", action="store_true", help="Show country presets from countries.json and exit")
    parser.add_argument("--list-colleges", metavar="COUNTRY", help="List colleges available for a given country and exit")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "id_card.png",
        help="Output path for the generated image (default: receipts/id_card.png)",
    )
    return parser.parse_args()


def require_fields(args: argparse.Namespace) -> None:
    missing = [
        name
        for name in [
            "student_name",
            "class_name",
            "phone",
            "ttl",
            "student_id",
            "address",
            "admission_period",
            "country",
            "contact_info",
        ]
        if getattr(args, name) is None
    ]
    if missing:
        raise SystemExit(f"Missing required fields: {', '.join(missing)}")


def main() -> None:
    presets = load_country_presets()
    args = parse_args()
    if args.list_colleges:
        preset = presets.get(args.list_colleges.strip().lower())
        if not preset:
            raise SystemExit(f"Country not found: {args.list_colleges}")
        colleges = preset.get("colleges", [])
        if colleges:
            print(f"Colleges for {args.list_colleges}:")
            for item in colleges:
                print(f"- {item}")
        else:
            college = preset.get("college", "")
            if college:
                print(f"College for {args.list_colleges}: {college}")
            else:
                print(f"No colleges configured for {args.list_colleges}")
        return
    if args.list_countries:
        print("Available country presets:")
        for name in sorted(presets):
            preset = presets[name]
            college_label = ""
            colleges = preset.get("colleges", [])
            if colleges:
                college_label = f" ({colleges[0]} + {len(colleges) - 1} more)" if len(colleges) > 1 else f" ({colleges[0]})"
            elif preset.get("college"):
                college_label = f" ({preset['college']})"
            print(f"- {preset.get('flag', '')} {name.title()}{college_label}")
        return

    require_fields(args)
    country, country_flag, preset_college, preset_colleges = resolve_country_inputs(args.country, args.country_flag, presets)
    college_name = args.college_name or preset_college or (preset_colleges[0] if preset_colleges else "")
    if not college_name:
        raise SystemExit("College name is required (provide it or set a preset college in countries.json)")
    data = CardData(
        college_name=college_name,
        student_name=args.student_name,
        alias=args.alias,
        class_name=args.class_name,
        phone=args.phone,
        ttl=args.ttl,
        student_id=args.student_id,
        address=args.address,
        admission_period=args.admission_period,
        country=country,
        country_flag=country_flag,
        contact_info=args.contact_info,
        photo_path=args.photo,
    )
    render_card(data, args.output)


if __name__ == "__main__":
    main()

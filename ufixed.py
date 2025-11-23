#!/usr/bin/env python3
"""Render student ID cards on the shared template with consistent layout.

This renderer keeps the same layout for every country. It overlays the
college name, student name, and supporting details onto the shared
``mentahan.jpg`` template while allowing callers to swap country labels
without altering the design.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent / "mentahan.jpg"
DEFAULT_OUTPUT_DIR = Path("receipts")

# Common country presets so callers can reuse the same layout without retyping flags.
COUNTRY_PRESETS: Dict[str, str] = {
    "indonesia": "🇮🇩",
    "malaysia": "🇲🇾",
    "singapore": "🇸🇬",
    "india": "🇮🇳",
    "philippines": "🇵🇭",
    "thailand": "🇹🇭",
    "vietnam": "🇻🇳",
    "brunei": "🇧🇳",
    "pakistan": "🇵🇰",
    "bangladesh": "🇧🇩",
    "sri lanka": "🇱🇰",
    "nepal": "🇳🇵",
    "myanmar": "🇲🇲",
    "cambodia": "🇰🇭",
    "laos": "🇱🇦",
    "china": "🇨🇳",
    "japan": "🇯🇵",
    "south korea": "🇰🇷",
}


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


def resolve_country_inputs(country: str, country_flag: str | None) -> Tuple[str, str]:
    """Return a normalized country name and flag.

    The layout stays the same for every country; this helper simply keeps
    the previous country list available so callers can skip typing flags.
    """

    normalized = country.strip()
    if country_flag:
        return normalized, country_flag

    preset = COUNTRY_PRESETS.get(normalized.lower())
    if preset:
        return normalized, preset

    logger.warning("No preset flag found for %s; leaving flag blank", normalized)
    return normalized, ""


def paste_photo(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    data: CardData,
    area: Tuple[int, int, int, int],
    require_photo: bool = False,
) -> None:
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

    if require_photo:
        raise FileNotFoundError("Photo is required but could not be loaded; check the --photo path")

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


def render_card(data: CardData, output_path: Path, require_photo: bool = False) -> Path:
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
    paste_photo(base, draw, data, photo_area, require_photo=require_photo)

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
    parser.add_argument("college_name", nargs="?", help="College name to display at the top")
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
    parser.add_argument(
        "--require-photo",
        action="store_true",
        help="Fail if the photo cannot be loaded (useful when uploads are mandatory)",
    )
    parser.add_argument(
        "--list-countries",
        action="store_true",
        help="Show built-in country presets and exit",
    )
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
            "college_name",
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
    args = parse_args()
    if args.list_countries:
        print("Available country presets:")
        for name, flag in sorted(COUNTRY_PRESETS.items()):
            print(f"- {flag} {name.title()}")
        return

    if args.require_photo and not args.photo:
        raise SystemExit("--require-photo is set but no --photo path was provided")

    require_fields(args)
    country, country_flag = resolve_country_inputs(args.country, args.country_flag)
    data = CardData(
        college_name=args.college_name,
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
    render_card(data, args.output, require_photo=args.require_photo)


if __name__ == "__main__":
    main()

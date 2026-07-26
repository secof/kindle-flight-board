import io
import os
import logging
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.config import settings
from app.models import FlightBoardData, Flight

logger = logging.getLogger("kindle-flight-board.renderer")


class BoardRenderer:
    def __init__(self):
        self.width = settings.BOARD_WIDTH
        self.height = settings.BOARD_HEIGHT
        self._fonts_loaded = False
        self._font_title = None
        self._font_header = None
        self._font_row_bold = None
        self._font_row_medium = None
        self._font_row_small = None
        self._font_badge = None
        self._font_time_large = None

    def _init_fonts(self):
        """Load doubled font sizes for maximum e-ink readability."""
        w = self.width
        title_size = max(24, int(w * 0.050))
        header_size = max(18, int(w * 0.030))
        bold_size = max(26, int(w * 0.056))        # ~45px at 800w
        time_large_size = max(32, int(w * 0.066))   # ~53px at 800w
        route_size = max(22, int(w * 0.046))        # ~37px at 800w
        medium_size = max(18, int(w * 0.032))       # ~26px at 800w
        small_size = max(16, int(w * 0.028))        # ~22px at 800w
        badge_size = max(16, int(w * 0.030))        # ~24px at 800w

        font_dir = settings.ASSETS_DIR / "fonts"
        ttf_files = list(font_dir.glob("*.ttf")) if font_dir.exists() else []

        if ttf_files:
            font_path = str(ttf_files[0])
            try:
                self._font_title = ImageFont.truetype(font_path, title_size)
                self._font_header = ImageFont.truetype(font_path, header_size)
                self._font_row_bold = ImageFont.truetype(font_path, bold_size)
                self._font_time_large = ImageFont.truetype(font_path, time_large_size)
                self._font_route = ImageFont.truetype(font_path, route_size)
                self._font_row_medium = ImageFont.truetype(font_path, medium_size)
                self._font_row_small = ImageFont.truetype(font_path, small_size)
                self._font_badge = ImageFont.truetype(font_path, badge_size)
                self._fonts_loaded = True
                return
            except Exception as e:
                logger.warning("Failed to load TTF font %s: %s", font_path, str(e))

        # Fallback to PIL default font
        default_font = ImageFont.load_default()
        self._font_title = default_font
        self._font_header = default_font
        self._font_row_bold = default_font
        self._font_time_large = default_font
        self._font_route = default_font
        self._font_row_medium = default_font
        self._font_row_small = default_font
        self._font_badge = default_font
        self._fonts_loaded = True

    def _get_aliases_map(self) -> dict:
        """Cache and return the alias dictionary from assets/logos/aliases.json if present."""
        if hasattr(self, "_aliases_map") and self._aliases_map is not None:
            return self._aliases_map

        aliases_file = settings.LOGOS_DIR / "aliases.json"
        if aliases_file.exists():
            try:
                import json
                with open(aliases_file, "r", encoding="utf-8") as f:
                    self._aliases_map = json.load(f)
                    return self._aliases_map
            except Exception as e:
                logger.warning("Failed to load aliases.json: %s", e)

        self._aliases_map = {}
        return self._aliases_map

    def _load_airline_logo(
        self, airline_icao: str, flight_number: str, max_width: int, max_height: int
    ) -> Image.Image:
        """Load logo from assets/logos/ using ICAO, flight number prefix, or alias mappings."""
        candidates = []

        if airline_icao:
            candidates.append(airline_icao.upper())

        if flight_number and len(flight_number) >= 2:
            prefix = flight_number.strip().split()[0][:2].upper()
            if prefix.isalnum() and prefix not in candidates:
                candidates.append(prefix)

        # Expand candidates with alias mapping
        aliases_map = self._get_aliases_map()
        for cand in list(candidates):
            for primary, aliases in aliases_map.items():
                if cand == primary or cand in aliases:
                    if primary not in candidates:
                        candidates.append(primary)
                    for alt in aliases:
                        if alt not in candidates:
                            candidates.append(alt)

        target_file = None
        for code in candidates:
            path = settings.LOGOS_DIR / f"{code}.png"
            if path.exists():
                target_file = path
                break

        if not target_file:
            default_logo_path = settings.LOGOS_DIR / "DEFAULT.png"
            if default_logo_path.exists():
                target_file = default_logo_path

        if target_file:
            try:
                logo_img = Image.open(target_file).convert("RGBA")
                logo_img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                # Solid white background (alpha=255) to prevent eips transparency bleed-through
                canvas = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 255))
                offset_x = (max_width - logo_img.width) // 2
                offset_y = (max_height - logo_img.height) // 2
                canvas.paste(logo_img, (offset_x, offset_y), logo_img)
                return canvas.convert("L")
            except Exception as e:
                logger.warning("Failed to load logo image %s: %s", target_file, str(e))

        # Fallback badge logo with solid white background
        badge = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(badge)
        draw.rounded_rectangle([2, 2, max_width - 2, max_height - 2], radius=8, outline=(0, 0, 0, 255), width=3)
        draw.rectangle([6, 6, max_width - 6, max_height - 6], fill=(235, 235, 235, 255))
        
        text = (airline_icao[:3] if airline_icao else flight_number[:2]).upper()
        draw.text((max_width // 2, max_height // 2), text, fill=(0, 0, 0, 255), font=self._font_row_medium, anchor="mm")
        return badge.convert("L")

    def _draw_plane_icon(self, draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, flight_type: str):
        """Draw clean, universal airplane taking off (DEP) or landing (ARR) vector icon without box or label."""
        is_dep = (flight_type == "DEP")
        
        # Baseline runway
        draw.line([(x + 2, y + h - 4), (x + w - 2, y + h - 4)], fill=0, width=5)
        
        if is_dep:
            # Airplane taking off (angled 30 deg up-right)
            draw.line([(x + 10, y + h - 18), (x + w - 10, y + 16)], fill=0, width=8)
            cx, cy = x + w // 2 + 2, y + h // 2 - 2
            draw.line([(cx - 8, cy - 14), (cx + 10, cy + 12)], fill=0, width=7)
            draw.line([(x + 14, y + h - 16), (x + 18, y + h - 34)], fill=0, width=6)
        else:
            # Airplane landing (angled 30 deg down-right)
            draw.line([(x + 10, y + 16), (x + w - 10, y + h - 18)], fill=0, width=8)
            cx, cy = x + w // 2 + 2, y + h // 2 - 2
            draw.line([(cx - 8, cy + 14), (cx + 10, cy - 12)], fill=0, width=7)
            draw.line([(x + 14, y + 16), (x + 18, y + 34)], fill=0, width=6)

    def render(self, data: FlightBoardData, rotate_override: Optional[int] = None) -> bytes:
        """Render high-contrast e-ink flight board (Doubled Fonts, Plane Icons, Big Time)."""
        self._init_fonts()

        w, h = self.width, self.height
        img = Image.new("L", (w, h), color=255)
        draw = ImageDraw.Draw(img)

        # 4 FLIGHT TABLE ROWS (HEADER & FOOTER REMOVED FOR MAXIMUM SPACE)
        row_height = h // 4
        flights = data.flights[:4]  # Exactly 4 flights

        # Proportional dimensions based on width and row height
        icon_w = int(w * 0.080)
        icon_h = int(row_height * 0.52)

        logo_w = int(w * 0.17)
        logo_h = int(row_height * 0.65)

        col_icon_x = int(w * 0.015)
        col_logo_x = col_icon_x + icon_w + int(w * 0.015)
        col_c_x = col_logo_x + logo_w + int(w * 0.025)   # Flight Number & Airline
        col_d_x = int(w * 0.510)                            # Time (Label on top, Big 54px Time)
        col_e_x = int(w * 0.680)                            # Route (Origin -> Destination)
        col_g_x = w - int(w * 0.015)                        # Live Status Pill (Right-aligned)

        for idx, flight in enumerate(flights):
            row_y1 = idx * row_height + 3
            row_y2 = row_y1 + row_height - 6
            bg_color = 255 if idx % 2 == 0 else 248

            # Outer Row Container Box
            draw.rounded_rectangle([int(w * 0.008), row_y1, w - int(w * 0.008), row_y2], radius=10, fill=bg_color, outline=0, width=2)

            # Col A: Universal Plane Icon (Taking off / Landing, no box, no text label)
            icon_y = row_y1 + (row_height - 6 - icon_h) // 2
            self._draw_plane_icon(draw, col_icon_x, icon_y, icon_w, icon_h, flight.flight_type)

            # Col B: Airline Logo (Bigger!)
            logo_img = self._load_airline_logo(flight.airline_icao, flight.flight_number, logo_w, logo_h)
            logo_y = row_y1 + (row_height - 6 - logo_h) // 2
            img.paste(logo_img, (col_logo_x, logo_y))

            y_top_text = row_y1 + int(row_height * 0.14)
            y_mid_time = row_y1 + int(row_height * 0.38)
            y_sub_text = row_y1 + int(row_height * 0.60)

            # Col C: Flight Number & Airline Name (BIGGER Font, No extra labels)
            draw.text((col_c_x, y_top_text), flight.flight_number, fill=0, font=self._font_row_bold)
            draw.text((col_c_x, y_sub_text), flight.airline_name[:16], fill=90, font=self._font_row_medium)

            # Col D: Time (Label ON TOP of Time, DOUBLED Time Text!)
            time_label = "DEP TIME" if flight.flight_type == "DEP" else "ARR TIME"
            draw.text((col_d_x, y_top_text), time_label, fill=90, font=self._font_row_small)
            draw.text((col_d_x, y_mid_time), flight.scheduled_time, fill=0, font=self._font_time_large)

            # Col E: Route (Origin ✈ Destination, BIGGER Font, No extra labels)
            route_str = f"{flight.origin} ✈ {flight.destination}"
            draw.text((col_e_x, y_top_text), route_str, fill=0, font=self._font_route)
            if flight.aircraft_type:
                draw.text((col_e_x, y_sub_text), flight.aircraft_type, fill=100, font=self._font_row_medium)

            # Col F: Live Status Pill (Right-Aligned)
            badge_w, badge_h = int(w * 0.135), int(row_height * 0.38)
            badge_rect = [col_g_x - badge_w, row_y1 + int(row_height * 0.31), col_g_x, row_y1 + int(row_height * 0.31) + badge_h]
            
            is_delayed = "Delay" in flight.status or "Late" in flight.status
            status_bg = 0 if is_delayed else 225
            status_fg = 255 if is_delayed else 0
            
            draw.rounded_rectangle(badge_rect, radius=8, fill=status_bg, outline=0, width=2)
            draw.text((col_g_x - badge_w // 2, row_y1 + int(row_height * 0.31) + badge_h // 2), flight.status[:16], fill=status_fg, font=self._font_badge, anchor="mm")

        # Apply rotation if configured
        rotation = rotate_override if rotate_override is not None else settings.ROTATE_DEGREES
        if rotation in (90, 180, 270):
            img = img.rotate(rotation, expand=True)

        # Apply color inversion if requested
        if settings.INVERT_COLORS:
            img = ImageOps.invert(img)

        # Export to 100% opaque PNG buffer
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="PNG", optimize=True)
        return output_buffer.getvalue()


renderer = BoardRenderer()

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
        self._font_route = None

    def _get_ttf_font(self, font_path: Optional[str], size: int) -> ImageFont.FreeTypeFont:
        """Attempt to load TTF font at specific pixel size, falling back to system TTF fonts or PIL load_default(size)."""
        if font_path and os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception as e:
                logger.warning("Failed to load TTF font %s (size %d): %s", font_path, size, str(e))
        
        system_fonts = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf"
        ]
        for sys_f in system_fonts:
            if os.path.exists(sys_f):
                try:
                    return ImageFont.truetype(sys_f, size)
                except Exception:
                    pass

        try:
            return ImageFont.load_default(size=size)
        except Exception:
            return ImageFont.load_default()

    def _init_fonts(self):
        """Load balanced scalable TTF fonts for clean e-ink readability."""
        w = self.width
        title_size = max(18, int(w * 0.040))
        header_size = max(14, int(w * 0.025))
        bold_size = max(18, int(w * 0.042))         # ~34px at 800w
        time_large_size = max(20, int(w * 0.048))   # ~38px at 800w
        route_size = max(18, int(w * 0.040))        # ~32px at 800w
        medium_size = max(14, int(w * 0.024))       # ~20px at 800w
        small_size = max(12, int(w * 0.020))        # ~16px at 800w
        badge_size = max(16, int(w * 0.040))        # ~32px at 800w

        font_dir = settings.ASSETS_DIR / "fonts"
        ttf_files = list(font_dir.glob("*.ttf")) + list(font_dir.glob("*.ttc")) if font_dir.exists() else []
        font_path = str(ttf_files[0]) if ttf_files else None

        self._font_title = self._get_ttf_font(font_path, title_size)
        self._font_header = self._get_ttf_font(font_path, header_size)
        self._font_row_bold = self._get_ttf_font(font_path, bold_size)
        self._font_time_large = self._get_ttf_font(font_path, time_large_size)
        self._font_route = self._get_ttf_font(font_path, route_size)
        self._font_row_medium = self._get_ttf_font(font_path, medium_size)
        self._font_row_small = self._get_ttf_font(font_path, small_size)
        self._font_badge = self._get_ttf_font(font_path, badge_size)
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
                
                # Solid pure white background (alpha=255) to prevent eips transparency bleed-through
                canvas = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 255))
                offset_x = (max_width - logo_img.width) // 2
                offset_y = (max_height - logo_img.height) // 2
                canvas.paste(logo_img, (offset_x, offset_y), logo_img)
                return canvas.convert("L")
            except Exception as e:
                logger.warning("Failed to load logo image %s: %s", target_file, str(e))

        # Fallback badge logo with solid pure white background
        badge = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(badge)
        draw.rounded_rectangle([2, 2, max_width - 2, max_height - 2], radius=8, outline=(0, 0, 0, 255), width=3)
        draw.rectangle([6, 6, max_width - 6, max_height - 6], fill=(255, 255, 255, 255))
        
        text = (airline_icao[:3] if airline_icao else flight_number[:2]).upper()
        draw.text((max_width // 2, max_height // 2), text, fill=(0, 0, 0, 255), font=self._font_row_medium, anchor="mm")
        return badge.convert("L")

    def _load_plane_icon(self, flight_type: str, max_width: int, max_height: int) -> Image.Image:
        """Load departure.png or landing.png from assets/plane/ and render onto solid pure white background."""
        filename = "departure.png" if flight_type == "DEP" else "landing.png"
        icon_path = settings.ASSETS_DIR / "plane" / filename

        if icon_path.exists():
            try:
                icon_img = Image.open(icon_path).convert("RGBA")
                icon_img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                # Solid pure white canvas (alpha=255) to prevent eips transparency bleed-through
                canvas = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 255))
                offset_x = (max_width - icon_img.width) // 2
                offset_y = (max_height - icon_img.height) // 2
                canvas.paste(icon_img, (offset_x, offset_y), icon_img)
                return canvas.convert("L")
            except Exception as e:
                logger.warning("Failed to load plane icon %s: %s", icon_path, str(e))

        # Fallback if file missing
        fallback = Image.new("L", (max_width, max_height), 255)
        draw = ImageDraw.Draw(fallback)
        text = "DEP" if flight_type == "DEP" else "ARR"
        draw.text((max_width // 2, max_height // 2), text, fill=0, font=self._font_badge, anchor="mm")
        return fallback

    def render(self, data: FlightBoardData, rotate_override: Optional[int] = None) -> bytes:
        """Render high-contrast e-ink flight board with 100% pure white background."""
        self._init_fonts()

        w, h = self.width, self.height
        # Main background: 100% pure white (color=255)
        img = Image.new("L", (w, h), color=255)
        draw = ImageDraw.Draw(img)

        # 4 FLIGHT TABLE ROWS (HEADER & FOOTER REMOVED FOR MAXIMUM SPACE)
        row_height = h // 4
        flights = data.flights[:4]  # Exactly 4 flights

        # Proportional dimensions based on width and row height
        icon_w = int(w * 0.085)
        icon_h = int(row_height * 0.65)

        logo_w = int(w * 0.150)
        logo_h = int(row_height * 0.65)

        # EQUALLY SPACED COLUMN POSITIONS
        col_icon_x = int(w * 0.018)     # ~14px
        col_logo_x = int(w * 0.135)     # ~108px
        col_c_x = int(w * 0.315)        # ~252px (Flight Number & Airline)
        col_d_x = int(w * 0.520)        # ~416px (Scheduled Time)
        col_e_x = int(w * 0.685)        # ~548px (Destination / Origin Airport)
        col_g_x = int(w * 0.982)        # ~785px (Live Status 2-row text, right-aligned)

        for idx, flight in enumerate(flights):
            row_y1 = idx * row_height + 3
            row_y2 = row_y1 + row_height - 6
            # 100% Pure White Background for all rows (fill=255)
            bg_color = 255

            # Outer Row Container Box
            draw.rounded_rectangle([int(w * 0.008), row_y1, w - int(w * 0.008), row_y2], radius=10, fill=bg_color, outline=0, width=2)

            # Col A: Plane Icon (departure.png or landing.png from assets/plane/)
            plane_icon = self._load_plane_icon(flight.flight_type, icon_w, icon_h)
            icon_y = row_y1 + (row_height - 6 - icon_h) // 2
            img.paste(plane_icon, (col_icon_x, icon_y))

            # Col B: Airline Logo
            logo_img = self._load_airline_logo(flight.airline_icao, flight.flight_number, logo_w, logo_h)
            logo_y = row_y1 + (row_height - 6 - logo_h) // 2
            img.paste(logo_img, (col_logo_x, logo_y))

            y_top_text = row_y1 + int(row_height * 0.22)
            y_mid_time = row_y1 + int(row_height * 0.35)
            y_sub_text = row_y1 + int(row_height * 0.60)

            # Col C: Flight Number & Airline Name
            draw.text((col_c_x, y_top_text), flight.flight_number, fill=0, font=self._font_row_bold)
            draw.text((col_c_x, y_sub_text), flight.airline_name[:16], fill=90, font=self._font_row_medium)

            # Col D: Scheduled Time (BIG Time Text, NO Label)
            draw.text((col_d_x, y_mid_time), flight.scheduled_time, fill=0, font=self._font_time_large)

            # Col E: Target Airport ONLY (Destination for DEP, Origin for ARR)
            target_airport = flight.destination if flight.flight_type == "DEP" else flight.origin
            draw.text((col_e_x, y_top_text), target_airport, fill=0, font=self._font_route)
            if flight.aircraft_type:
                draw.text((col_e_x, y_sub_text), flight.aircraft_type, fill=100, font=self._font_row_medium)

            # Col F: Live Status Text (2 rows: Row 1 = EST or DLY, Row 2 = Time)
            status_raw = flight.status.strip()
            is_delayed = ("Delay" in status_raw) or ("Late" in status_raw) or ("CANCEL" in status_raw.upper())
            
            status_label = "DLY" if is_delayed else "EST"
            status_time = flight.estimated_time or flight.scheduled_time

            draw.text((col_g_x, y_top_text), status_label, fill=90, font=self._font_row_small, anchor="rt")
            draw.text((col_g_x, y_sub_text), status_time, fill=0, font=self._font_route, anchor="rt")

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

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

    def _init_fonts(self):
        """Load default PIL fonts or custom TTF fonts if present in assets/fonts."""
        if self._fonts_loaded:
            return

        font_dir = settings.ASSETS_DIR / "fonts"
        ttf_files = list(font_dir.glob("*.ttf")) if font_dir.exists() else []

        if ttf_files:
            font_path = str(ttf_files[0])
            try:
                self._font_title = ImageFont.truetype(font_path, 40)
                self._font_header = ImageFont.truetype(font_path, 26)
                self._font_row_bold = ImageFont.truetype(font_path, 34)
                self._font_row_medium = ImageFont.truetype(font_path, 25)
                self._font_row_small = ImageFont.truetype(font_path, 19)
                self._font_badge = ImageFont.truetype(font_path, 22)
                self._fonts_loaded = True
                return
            except Exception as e:
                logger.warning("Failed to load TTF font %s: %s", font_path, str(e))

        # Fallback to PIL default font
        default_font = ImageFont.load_default()
        self._font_title = default_font
        self._font_header = default_font
        self._font_row_bold = default_font
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

    def render(self, data: FlightBoardData, rotate_override: Optional[int] = None) -> bytes:
        """Render high-contrast landscape e-ink flight board to PNG bytes."""
        self._init_fonts()

        img = Image.new("L", (self.width, self.height), color=255)
        draw = ImageDraw.Draw(img)

        # 1. HEADER SECTION
        header_height = 130
        draw.rectangle([0, 0, self.width, header_height], fill=245)
        
        # Title & Airport Name
        draw.text((40, 22), f"✈  {data.airport_name.upper()} ({data.airport_icao})", fill=0, font=self._font_title)
        draw.text((40, 78), "UPCOMING FLIGHT DEPARTURES & ARRIVALS", fill=80, font=self._font_header)

        # Metadata & Status Pill
        meta_str = f"UPDATED: {data.last_updated}"
        draw.text((self.width - 40, 32), meta_str, fill=60, font=self._font_row_small, anchor="rt")
        
        status_pill_rect = [self.width - 270, 68, self.width - 40, 106]
        draw.rounded_rectangle(status_pill_rect, radius=6, fill=0)
        draw.text((self.width - 155, 87), "LIVE • FLIGHTRADAR24", fill=255, font=self._font_row_small, anchor="mm")

        # Dividing header line
        draw.line([(0, header_height), (self.width, header_height)], fill=0, width=4)

        # 2. FLIGHT TABLE ROWS (Exactly 4 upcoming flights)
        table_top = header_height + 12
        table_bottom = self.height - 40
        total_table_height = table_bottom - table_top
        row_height = total_table_height // 4

        flights = data.flights[:4]  # Exactly 4 flights

        for idx, flight in enumerate(flights):
            row_y1 = table_top + idx * row_height
            row_y2 = row_y1 + row_height - 10
            bg_color = 255 if idx % 2 == 0 else 248

            # Outer Row Container Box
            draw.rounded_rectangle([20, row_y1, self.width - 20, row_y2], radius=10, fill=bg_color, outline=0, width=2)

            # Col A: Flight Type Badge (DEP ↗ / ARR ↘)
            type_pill_w, type_pill_h = 105, 48
            type_x1 = 35
            type_y1 = row_y1 + (row_height - 10 - type_pill_h) // 2
            type_x2 = type_x1 + type_pill_w
            type_y2 = type_y1 + type_pill_h
            
            if flight.flight_type == "DEP":
                draw.rounded_rectangle([type_x1, type_y1, type_x2, type_y2], radius=6, fill=0)
                draw.text(((type_x1 + type_x2) // 2, (type_y1 + type_y2) // 2), "DEP ↗", fill=255, font=self._font_badge, anchor="mm")
            else:
                draw.rounded_rectangle([type_x1, type_y1, type_x2, type_y2], radius=6, fill=220, outline=0, width=2)
                draw.text(((type_x1 + type_x2) // 2, (type_y1 + type_y2) // 2), "ARR ↘", fill=0, font=self._font_badge, anchor="mm")

            # Col B: Airline Logo (Width ~ 110px)
            logo_w, logo_h = 110, 70
            logo_img = self._load_airline_logo(flight.airline_icao, flight.flight_number, logo_w, logo_h)
            logo_x = 155
            logo_y = row_y1 + (row_height - 10 - logo_h) // 2
            img.paste(logo_img.convert("L"), (logo_x, logo_y))

            # Col C: Flight Number & Airline Name
            col_c_x = 280
            draw.text((col_c_x, row_y1 + 42), flight.flight_number, fill=0, font=self._font_row_bold)
            draw.text((col_c_x, row_y1 + 92), flight.airline_name[:20], fill=90, font=self._font_row_small)

            # Col D: Scheduled Time (SCHED)
            col_d_x = 510
            draw.text((col_d_x, row_y1 + 42), flight.scheduled_time, fill=0, font=self._font_row_bold)
            draw.text((col_d_x, row_y1 + 92), "SCHED TIME", fill=110, font=self._font_row_small)

            # Col E: Route (Origin -> Destination)
            col_e_x = 690
            route_str = f"{flight.origin}  ✈  {flight.destination}"
            draw.text((col_e_x, row_y1 + 42), route_str, fill=0, font=self._font_row_bold)
            route_sub = "DEPARTURE" if flight.flight_type == "DEP" else "ARRIVAL"
            draw.text((col_e_x, row_y1 + 92), f"FLIGHT {route_sub}", fill=90, font=self._font_row_small)

            # Col F: Aircraft Type
            col_f_x = 1010
            draw.text((col_f_x, row_y1 + 42), flight.aircraft_type, fill=0, font=self._font_row_medium)
            draw.text((col_f_x, row_y1 + 92), "AIRCRAFT", fill=110, font=self._font_row_small)

            # Col G: Live Status Pill (Right-Aligned)
            col_g_x = self.width - 45
            badge_w, badge_h = 230, 50
            badge_rect = [col_g_x - badge_w, row_y1 + 40, col_g_x, row_y1 + 40 + badge_h]
            
            is_delayed = "Delay" in flight.status or "Late" in flight.status
            status_bg = 0 if is_delayed else 225
            status_fg = 255 if is_delayed else 0
            
            draw.rounded_rectangle(badge_rect, radius=8, fill=status_bg, outline=0, width=2)
            draw.text((col_g_x - badge_w // 2, row_y1 + 40 + badge_h // 2), flight.status[:22], fill=status_fg, font=self._font_row_small, anchor="mm")

        # 3. FOOTER SECTION
        footer_y = self.height - 32
        draw.line([(20, footer_y - 8), (self.width - 20, footer_y - 8)], fill=180, width=1)
        draw.text((40, footer_y), f"Kindle Paperwhite Display (FW 5.17)  •  Flightradar24 API  •  Timezone: {settings.TIMEZONE}", fill=120, font=self._font_row_small)
        draw.text((self.width - 40, footer_y), f"HASH: {data.data_hash}", fill=120, font=self._font_row_small, anchor="rt")

        # Apply rotation if configured
        rotation = rotate_override if rotate_override is not None else settings.ROTATE_DEGREES
        if rotation in (90, 180, 270):
            img = img.rotate(rotation, expand=True)

        # Apply color inversion if requested
        if settings.INVERT_COLORS:
            img = ImageOps.invert(img)

        # Export to PNG buffer
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="PNG", optimize=True)
        return output_buffer.getvalue()


renderer = BoardRenderer()

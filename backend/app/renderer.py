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

    def _init_fonts(self):
        """Load default PIL fonts or custom TTF fonts if present in assets/fonts."""
        if self._fonts_loaded:
            return

        font_dir = settings.ASSETS_DIR / "fonts"
        ttf_files = list(font_dir.glob("*.ttf")) if font_dir.exists() else []

        if ttf_files:
            font_path = str(ttf_files[0])
            try:
                self._font_title = ImageFont.truetype(font_path, 42)
                self._font_header = ImageFont.truetype(font_path, 28)
                self._font_row_bold = ImageFont.truetype(font_path, 34)
                self._font_row_medium = ImageFont.truetype(font_path, 26)
                self._font_row_small = ImageFont.truetype(font_path, 20)
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
        self._fonts_loaded = True

    def _load_airline_logo(self, airline_icao: str, max_width: int, max_height: int) -> Image.Image:
        """Load logo from assets/logos/{ICAO}.png or render fallback badge."""
        logo_path = settings.LOGOS_DIR / f"{airline_icao.upper()}.png"
        default_logo_path = settings.LOGOS_DIR / "DEFAULT.png"

        target_file = logo_path if logo_path.exists() else (default_logo_path if default_logo_path.exists() else None)

        if target_file:
            try:
                logo_img = Image.open(target_file).convert("RGBA")
                logo_img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                # Create white canvas for alpha blending
                canvas = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 0))
                offset_x = (max_width - logo_img.width) // 2
                offset_y = (max_height - logo_img.height) // 2
                canvas.paste(logo_img, (offset_x, offset_y), logo_img)
                return canvas
            except Exception as e:
                logger.warning("Failed to load logo image %s: %s", target_file, str(e))

        # Dynamic fallback vector/text badge logo
        badge = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(badge)
        
        # Draw rounded rectangle badge
        draw.rounded_rectangle([4, 4, max_width - 4, max_height - 4], radius=8, outline=(0, 0, 0, 255), width=3)
        draw.rectangle([8, 8, max_width - 8, max_height - 8], fill=(230, 230, 230, 255))
        
        # Render initials text inside badge
        text = airline_icao[:3].upper()
        draw.text((max_width // 2, max_height // 2), text, fill=(0, 0, 0, 255), font=self._font_row_medium, anchor="mm")
        return badge

    def render(self, data: FlightBoardData) -> bytes:
        """Render complete landscape flight board to PNG bytes."""
        self._init_fonts()

        # Create high-contrast grayscale image (8-bit 'L' mode)
        img = Image.new("L", (self.width, self.height), color=255)
        draw = ImageDraw.Draw(img)

        # 1. HEADER SECTION
        header_height = 130
        draw.rectangle([0, 0, self.width, header_height], fill=245)
        
        # Top title & Airport Name
        draw.text((40, 24), f"✈  {data.airport_name.upper()} ({data.airport_icao})", fill=0, font=self._font_title)
        draw.text((40, 78), "FLIGHT DEPARTURES & ARRIVALS", fill=80, font=self._font_row_medium)

        # Right-aligned header metadata
        meta_str = f"UPDATED: {data.last_updated}"
        draw.text((self.width - 40, 36), meta_str, fill=60, font=self._font_row_small, anchor="rt")
        
        status_pill_rect = [self.width - 270, 72, self.width - 40, 108]
        draw.rounded_rectangle(status_pill_rect, radius=6, fill=0)
        draw.text((self.width - 155, 90), "LIVE • FLIGHTRADAR24", fill=255, font=self._font_row_small, anchor="mm")

        # Dividing line
        draw.line([(0, header_height), (self.width, header_height)], fill=0, width=4)

        # 2. FLIGHT TABLE ROWS (Exactly 4 flights)
        table_top = header_height + 10
        table_bottom = self.height - 40
        total_table_height = table_bottom - table_top
        row_height = total_table_height // 4

        flights = data.flights[:4]  # Safety cap to 4

        for idx, flight in enumerate(flights):
            row_y1 = table_top + idx * row_height
            row_y2 = row_y1 + row_height - 10

            # Alternating background fill & past flight visual indicator
            if flight.is_past:
                bg_color = 238  # Light gray for past flight
            else:
                bg_color = 255 if idx % 2 == 0 else 248

            # Draw Row Box
            draw.rounded_rectangle([20, row_y1, self.width - 20, row_y2], radius=10, fill=bg_color, outline=0, width=2)

            # PAST flight indicator badge on the left edge
            if flight.is_past:
                draw.rounded_rectangle([20, row_y1, 32, row_y2], radius=4, fill=100)

            # Col A: Airline Logo (Width ~ 140px)
            logo_w, logo_h = 130, 80
            logo_img = self._load_airline_logo(flight.airline_icao, logo_w, logo_h)
            
            logo_x = 50
            logo_y = row_y1 + (row_height - 10 - logo_h) // 2
            
            # Paste RGBA logo onto L mode image
            img.paste(logo_img.convert("L"), (logo_x, logo_y))

            # Col B: Flight Number & Airline (Width ~ 280px)
            col_b_x = 210
            draw.text((col_b_x, row_y1 + 45), flight.flight_number, fill=0, font=self._font_row_bold)
            draw.text((col_b_x, row_y1 + 95), flight.airline_name[:20], fill=90, font=self._font_row_small)

            # Col C: Route (Origin -> Destination) (Width ~ 380px)
            col_c_x = 520
            route_str = f"{flight.origin}  ✈  {flight.destination}"
            draw.text((col_c_x, row_y1 + 45), route_str, fill=0, font=self._font_row_bold)
            draw.text((col_c_x, row_y1 + 95), f"GATE / TERM: T1", fill=90, font=self._font_row_small)

            # Col D: Aircraft Type (Width ~ 180px)
            col_d_x = 940
            draw.text((col_d_x, row_y1 + 45), flight.aircraft_type, fill=0, font=self._font_row_medium)
            draw.text((col_d_x, row_y1 + 95), "AIRCRAFT", fill=110, font=self._font_row_small)

            # Col E: Status Badge & Time (Right Aligned)
            col_e_x = self.width - 50
            
            status_bg = 0 if flight.is_past else (40 if "BOARD" in flight.status else 210)
            status_fg = 255 if flight.is_past or "BOARD" in flight.status else 0
            
            badge_w, badge_h = 240, 52
            badge_rect = [col_e_x - badge_w, row_y1 + 35, col_e_x, row_y1 + 35 + badge_h]
            
            draw.rounded_rectangle(badge_rect, radius=8, fill=status_bg, outline=0, width=2)
            draw.text((col_e_x - badge_w // 2, row_y1 + 35 + badge_h // 2), flight.status, fill=status_fg, font=self._font_row_medium, anchor="mm")

            if flight.is_past:
                draw.text((col_e_x - badge_w // 2, row_y1 + 98), "PAST FLIGHT", fill=100, font=self._font_row_small, anchor="mm")

        # 3. FOOTER SECTION
        footer_y = self.height - 32
        draw.line([(20, footer_y - 8), (self.width - 20, footer_y - 8)], fill=180, width=1)
        draw.text((40, footer_y), f"Kindle Paperwhite Display (FW 5.17)  •  Flightradar24 API  •  Timezone: {settings.TIMEZONE}", fill=120, font=self._font_row_small)
        draw.text((self.width - 40, footer_y), f"HASH: {data.data_hash}", fill=120, font=self._font_row_small, anchor="rt")

        # Apply rotation if configured
        if settings.ROTATE_DEGREES in (90, 180, 270):
            img = img.rotate(settings.ROTATE_DEGREES, expand=True)

        # Apply color inversion if requested
        if settings.INVERT_COLORS:
            img = ImageOps.invert(img)

        # Export to PNG buffer
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="PNG", optimize=True)
        return output_buffer.getvalue()


renderer = BoardRenderer()

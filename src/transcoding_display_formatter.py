# src/transcoding_display_formatter.py
import logging
from datetime import timedelta
from typing import Optional
import re # Dodano do format_filesize

logger = logging.getLogger(__name__)

class TranscodingDisplayFormatter:
    """
    Klasa odpowiedzialna za formatowanie danych związanych z postępem transkodowania
    do wyświetlenia w interfejsie użytkownika.
    """

    def __init__(self):
        logger.debug("TranscodingDisplayFormatter zainicjalizowany.")

    def format_progress_time(self, seconds: Optional[float]) -> str:
        """
        Formatuje czas w sekundach do czytelnego formatu HH:MM:SS.
        Jeśli sekundy to None, zwraca "??:??:??".
        """
        if seconds is None or seconds < 0:
            return "??:??:??"
        td = timedelta(seconds=int(seconds))
        hours, remainder = divmod(td.seconds, 3600)
        if td.days > 0:
            hours += td.days * 24
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def format_percentage(self, percentage: float) -> str:
        """
        Formatuje procent do wyświetlenia (np. z jednym miejscem po przecinku).
        """
        return f"{percentage:.1f}%"

    def format_fps(self, fps: Optional[float]) -> str:
        """
        Formatuje liczbę klatek na sekundę.
        """
        if fps is None:
            return "---- FPS"
        return f"{fps:.1f} FPS"

    def format_speed(self, speed: Optional[str]) -> str:
        """
        Formatuje wskaźnik prędkości przetwarzania.
        """
        if not speed or not speed.strip() or speed.upper() == "N/A":
            return "---x"
        cleaned_speed = speed.lower().replace('x', '')
        try:
            float(cleaned_speed)
            return f"{cleaned_speed}x"
        except ValueError:
            return speed

    def format_eta(self, eta_seconds: Optional[float]) -> str:
        """
        Formatuje szacowany czas pozostały (ETA) w sekundach do HH:MM:SS.
        """
        return self.format_progress_time(eta_seconds)

    def format_bitrate(self, bitrate: Optional[str]) -> str:
        """
        Formatuje bitrate.
        """
        if not bitrate or not bitrate.strip() or bitrate.upper() == "N/A":
            return "---- kbps" # Zmieniono domyślną jednostkę dla spójności
        cleaned_bitrate = bitrate.lower().replace('/s', '')
        if "kbits" in cleaned_bitrate:
            cleaned_bitrate = cleaned_bitrate.replace("kbits", "kbps")
        elif "mbits" in cleaned_bitrate:
             cleaned_bitrate = cleaned_bitrate.replace("mbits", "Mbps") # Duże 'M' dla Mega
        elif not cleaned_bitrate.endswith("bps") and not cleaned_bitrate.endswith("Bps") :
            try:
                # Prosta próba detekcji czy to liczba, aby dodać jednostkę
                # Usuń 'k' lub 'm' na początku, jeśli są, dla samej liczby
                numeric_part = cleaned_bitrate
                unit_prefix = ""
                if numeric_part.startswith('k'):
                    numeric_part = numeric_part[1:]
                    unit_prefix = "k"
                elif numeric_part.startswith('m'):
                    numeric_part = numeric_part[1:]
                    unit_prefix = "M"

                float(numeric_part) # Sprawdź czy reszta to liczba
                cleaned_bitrate = f"{cleaned_bitrate}{unit_prefix}bps"

            except ValueError:
                pass # Zostaw jak jest, jeśli nie jest to prosta liczba + opcjonalny prefix
        return cleaned_bitrate

    def format_filesize(self, size_str: Optional[str]) -> str:
        """
        Formatuje rozmiar pliku podany jako string z ffmpeg (np. "12345kB", "N/A").
        Konwertuje na czytelny format (KB, MB, GB).
        """
        if not size_str or not size_str.strip() or size_str.upper() == "N/A":
            return "---- MB"

        size_str_lower = size_str.lower()
        num_part_match = re.match(r"([\d\.]+)", size_str_lower)
        if not num_part_match:
            return "---- MB" # Nie udało się wyekstrahować liczby

        num_val = float(num_part_match.group(1))

        if "kb" in size_str_lower or "kib" in size_str_lower : # ffmpeg używa k i KiB zamiennie czasem
            size_bytes = num_val * 1024
        elif "mb" in size_str_lower or "mib" in size_str_lower:
            size_bytes = num_val * (1024**2)
        elif "gb" in size_str_lower or "gib" in size_str_lower:
            size_bytes = num_val * (1024**3)
        elif "b" in size_str_lower: # Tylko bajty
            size_bytes = num_val
        else: # Jeśli brak jednostki, załóżmy, że to kilobajty (najczęstsze w `size=`)
            try:
                size_bytes = num_val * 1024
            except ValueError:
                return "---- MB" # Błąd konwersji

        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/(1024**2):.1f} MB"
        else:
            return f"{size_bytes/(1024**3):.1f} GB"

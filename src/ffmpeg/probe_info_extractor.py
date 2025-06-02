# src/ffmpeg/probe_info_extractor.py
import subprocess
import logging
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from ..models import MediaInfo # Używamy modelu MediaInfo
from ..config_manager import ConfigManager # Potrzebny do ścieżki ffprobe

logger = logging.getLogger(__name__)

class ProbeInfoExtractor:
    """
    Wyodrębnia informacje o plikach multimedialnych używając FFprobe.
    """
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        ffprobe_path_config = self.config_manager.get_config_value('ffmpeg', 'ffprobe_path', 'ffprobe')
        if isinstance(ffprobe_path_config, Path):
            self.ffprobe_path = str(ffprobe_path_config.resolve())
        else:
            self.ffprobe_path = ffprobe_path_config
        logger.debug(f"ProbeInfoExtractor zainicjalizowany. Ścieżka FFprobe: {self.ffprobe_path}")

    def _verify_ffprobe_executable(self) -> bool:
        # (bez zmian od ostatniej poprawnej wersji)
        try:
            process = subprocess.Popen(
                [self.ffprobe_path, '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            stdout, stderr = process.communicate(timeout=5)
            if process.returncode == 0:
                logger.info(f"FFprobe zweryfikowany pomyślnie: {self.ffprobe_path}")
                return True
            else:
                logger.error(f"FFprobe nie powiódł się przy weryfikacji (kod: {process.returncode}). Ścieżka: {self.ffprobe_path}. Stderr: {stderr.strip()}")
                return False
        except FileNotFoundError:
            logger.error(f"Plik wykonywalny FFprobe nie znaleziony pod ścieżką: {self.ffprobe_path}. Sprawdź konfigurację i PATH.")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout podczas weryfikacji FFprobe: {self.ffprobe_path}")
            return False
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas weryfikacji FFprobe ({self.ffprobe_path}): {e}", exc_info=True)
            return False

    def get_media_info(self, file_path: Path) -> MediaInfo:
        """
        Pobiera informacje o medium dla danego pliku, używając FFprobe.
        Zwraca obiekt MediaInfo. Jeśli wystąpi błąd, obiekt MediaInfo
        będzie zawierał komunikat błędu w polu `error_message`.
        """
        logger.debug(f"Pobieranie informacji media dla pliku: {file_path}")
        if not self._verify_ffprobe_executable():
            error_msg = f"Plik wykonywalny FFprobe ('{self.ffprobe_path}') nie jest dostępny lub nie działa poprawnie."
            logger.error(error_msg)
            return MediaInfo(file_path=file_path, error_message=error_msg)

        if not file_path.exists() or not file_path.is_file():
            error_msg = f"Plik źródłowy nie istnieje lub nie jest plikiem: {file_path}"
            logger.error(error_msg)
            return MediaInfo(file_path=file_path, error_message=error_msg)

        command = [
            self.ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(file_path)
        ]

        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
            stdout, stderr = process.communicate(timeout=30)

            if process.returncode != 0:
                error_msg = f"FFprobe zakończył działanie z błędem (kod: {process.returncode}) dla pliku {file_path.name}. Szczegóły: {stderr.strip()}"
                logger.error(error_msg)
                return MediaInfo(file_path=file_path, error_message=error_msg)

            if not stdout:
                error_msg = f"FFprobe nie zwrócił żadnych danych (stdout pusty) dla pliku {file_path.name}."
                logger.warning(error_msg)
                return MediaInfo(file_path=file_path, error_message=error_msg)

            data = json.loads(stdout)

            duration: Optional[float] = None
            format_name_str: Optional[str] = None
            bit_rate_val: Optional[int] = None # <--- ZMIENNA DLA BIT_RATE

            if 'format' in data:
                if 'duration' in data['format']:
                    try:
                        duration = float(data['format']['duration'])
                    except (ValueError, TypeError):
                        logger.warning(f"Nie można sparsować czasu trwania z formatu FFprobe dla {file_path.name}: {data['format'].get('duration')}")

                format_name_str = data['format'].get('format_name')
                if format_name_str:
                    logger.debug(f"Odczytano format_name: '{format_name_str}' dla pliku {file_path.name}")

                # Pobieranie bit_rate
                bit_rate_str = data['format'].get('bit_rate') # <--- POBIERANIE BIT_RATE
                if bit_rate_str:
                    try:
                        bit_rate_val = int(bit_rate_str)
                        logger.debug(f"Odczytano bit_rate: {bit_rate_val} bps dla pliku {file_path.name}")
                    except ValueError:
                        logger.warning(f"Nie można sparsować bit_rate: '{bit_rate_str}' dla pliku {file_path.name}")


            video_codec: Optional[str] = None
            audio_codec: Optional[str] = None
            width: Optional[int] = None
            height: Optional[int] = None
            frame_rate_str: Optional[str] = None # <--- ZMIENNA DLA FRAME_RATE

            if 'streams' in data:
                for stream in data['streams']:
                    if stream.get('codec_type') == 'video' and video_codec is None: # Bierz pierwszy strumień wideo
                        video_codec = stream.get('codec_name')
                        width = stream.get('width')
                        height = stream.get('height')
                        # Pobieranie frame_rate (preferuj r_frame_rate, fallback na avg_frame_rate)
                        frame_rate_str = stream.get('r_frame_rate') # <--- POBIERANIE R_FRAME_RATE
                        if not frame_rate_str or frame_rate_str == "0/0": # Jeśli r_frame_rate jest nieprawidłowe lub brak
                            frame_rate_str = stream.get('avg_frame_rate') # <--- FALLBACK NA AVG_FRAME_RATE
                        if frame_rate_str:
                             logger.debug(f"Odczytano frame_rate: '{frame_rate_str}' dla strumienia wideo pliku {file_path.name}")


                        if duration is None and 'duration' in stream:
                            try:
                                duration = float(stream['duration'])
                            except (ValueError, TypeError):
                                logger.warning(f"Nie można sparsować czasu trwania ze strumienia wideo dla {file_path.name}: {stream.get('duration')}")
                    elif stream.get('codec_type') == 'audio' and audio_codec is None: # Bierz pierwszy strumień audio
                        audio_codec = stream.get('codec_name')

            if duration is None:
                logger.warning(f"Nie udało się ustalić czasu trwania dla pliku {file_path.name}.")


            return MediaInfo(
                file_path=file_path,
                duration=duration,
                video_codec=video_codec,
                audio_codec=audio_codec,
                width=width,
                height=height,
                format_name=format_name_str,
                bit_rate=bit_rate_val,         # <--- PRZEKAZANIE BIT_RATE
                frame_rate=frame_rate_str,     # <--- PRZEKAZANIE FRAME_RATE
                error_message=None
            )

        except subprocess.TimeoutExpired:
            error_msg = f"Przekroczono limit czasu FFprobe podczas analizy pliku {file_path.name}."
            logger.error(error_msg, exc_info=True)
            return MediaInfo(file_path=file_path, error_message=error_msg)
        except json.JSONDecodeError:
            error_msg = f"Błąd dekodowania JSON z wyjścia FFprobe dla pliku {file_path.name}. Wyjście: {stdout[:500]}..."
            logger.error(error_msg, exc_info=True)
            return MediaInfo(file_path=file_path, error_message=error_msg)
        except Exception as e:
            error_msg = f"Nieoczekiwany błąd podczas pobierania informacji o medium dla {file_path.name}: {e}"
            logger.critical(error_msg, exc_info=True)
            return MediaInfo(file_path=file_path, error_message=error_msg)

    def is_file_readable_by_ffprobe(self, file_path: Path) -> bool:
        # (bez zmian od ostatniej poprawnej wersji)
        logger.debug(f"Sprawdzanie czytelności pliku przez FFprobe: {file_path}")
        if not self._verify_ffprobe_executable():
            logger.error(f"FFprobe ('{self.ffprobe_path}') nie jest dostępne. Nie można sprawdzić czytelności pliku.")
            return False

        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"Plik do sprawdzenia czytelności nie istnieje lub nie jest plikiem: {file_path}")
            return False
        
        command = [
            self.ffprobe_path,
            '-v', 'error',
            str(file_path)
        ]
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False, encoding='utf-8')
            if process.returncode == 0:
                logger.info(f"Plik '{file_path.name}' jest czytelny przez FFprobe.")
                return True
            else:
                logger.warning(f"FFprobe zwrócił błąd (kod: {process.returncode}) podczas sprawdzania czytelności pliku '{file_path.name}'. Szczegóły: {process.stderr.strip()}")
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"Przekroczono limit czasu FFprobe podczas sprawdzania czytelności pliku {file_path.name}.")
            return False
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas sprawdzania czytelności pliku {file_path.name} przez FFprobe: {e}", exc_info=True)
            return False

# src/ffmpeg/ffmpeg_manager.py
import subprocess
import logging
import re
import time
from pathlib import Path
from typing import List, Optional, Callable, Tuple, Dict, Any, Union
import uuid # Potrzebne dla tymczasowego profilu w attempt_repair_file

from .probe_info_extractor import ProbeInfoExtractor
from .transcoder import Transcoder, ProgressCallbackType
from ..models import MediaInfo, EncodingProfile, RepairProfile
from ..config_manager import ConfigManager 

logger = logging.getLogger(__name__)

class FFmpegManager:
    def __init__(self, config_manager: ConfigManager, display_progress_callback: Optional[ProgressCallbackType] = None):
        logger.debug("FFmpegManager: Inicjalizacja rozpoczęta.")
        self.config_manager = config_manager
        self.probe_extractor = ProbeInfoExtractor(config_manager)
        self.transcoder = Transcoder(config_manager, display_progress_callback)
        
        self.mkvmerge_path: str = 'mkvmerge' 
        self.update_tool_paths_from_config()
             
        logger.debug("FFmpegManager: Inicjalizacja zakończona.")

    def update_tool_paths_from_config(self):
        logger.info("FFmpegManager: Aktualizowanie ścieżek narzędzi CLI z konfiguracji.")
        
        ffprobe_path_config = self.config_manager.get_config_value('ffmpeg', 'ffprobe_path', 'ffprobe')
        if isinstance(ffprobe_path_config, Path):
            self.probe_extractor.ffprobe_path = str(ffprobe_path_config.resolve())
        else:
            self.probe_extractor.ffprobe_path = str(ffprobe_path_config)
        logger.debug(f"FFmpegManager: Zaktualizowano ścieżkę FFprobe do: {self.probe_extractor.ffprobe_path}")
        if not self.probe_extractor._verify_ffprobe_executable():
            logger.error(f"FFprobe pod ścieżką '{self.probe_extractor.ffprobe_path}' nie jest dostępny lub nie działa.")

        ffmpeg_path_config = self.config_manager.get_config_value('ffmpeg', 'ffmpeg_path', 'ffmpeg')
        if isinstance(ffmpeg_path_config, Path):
            self.transcoder.ffmpeg_path = str(ffmpeg_path_config.resolve())
        else:
            self.transcoder.ffmpeg_path = str(ffmpeg_path_config)
        logger.debug(f"FFmpegManager: Zaktualizowano ścieżkę FFmpeg do: {self.transcoder.ffmpeg_path}")
        if not self.transcoder._verify_ffmpeg_executable():
            logger.error(f"FFmpeg pod ścieżką '{self.transcoder.ffmpeg_path}' nie jest dostępny lub nie działa.")

        mkvmerge_path_config = self.config_manager.get_config_value('ffmpeg', 'mkvmerge_path', 'mkvmerge')
        if isinstance(mkvmerge_path_config, Path):
            self.mkvmerge_path = str(mkvmerge_path_config.resolve())
        else:
            self.mkvmerge_path = str(mkvmerge_path_config)
        logger.debug(f"FFmpegManager: Zaktualizowano ścieżkę mkvmerge do: {self.mkvmerge_path}")
        if not self._verify_mkvmerge_executable():
             logger.error(f"Mkvmerge pod ścieżką '{self.mkvmerge_path}' nie jest dostępny lub nie działa.")

    def _verify_mkvmerge_executable(self) -> bool:
        try:
            process = subprocess.Popen([self.mkvmerge_path, '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
            stdout, stderr = process.communicate(timeout=5)
            if process.returncode == 0:
                logger.info(f"MKVmerge zweryfikowany pomyślnie: {self.mkvmerge_path}")
                return True
            else:
                logger.error(f"MKVmerge nie powiódł się przy weryfikacji (kod: {process.returncode}). Ścieżka: {self.mkvmerge_path}. Stderr: {stderr.strip()}")
                return False
        except FileNotFoundError:
            logger.error(f"Plik wykonywalny mkvmerge nie znaleziony: {self.mkvmerge_path}.")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout podczas weryfikacji mkvmerge: {self.mkvmerge_path}")
            return False
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd weryfikacji mkvmerge ({self.mkvmerge_path}): {e}", exc_info=True)
            return False

    def get_media_info(self, file_path: Path) -> MediaInfo:
        logger.debug(f"FFmpegManager: Pobieranie informacji media dla '{file_path.name}'.")
        return self.probe_extractor.get_media_info(file_path)

    def transcode_file(self,
                       input_file_path: Path, output_file_path: Path,
                       profile: EncodingProfile, media_info: MediaInfo,
                       file_index: Optional[int] = None, total_files_in_job: Optional[int] = None
                       ) -> Tuple[bool, Optional[str]]:
        logger.debug(f"FFmpegManager: Rozpoczynanie transkodowania dla '{input_file_path.name}'. Plik {file_index or 'N/A'}/{total_files_in_job or 'N/A'}.")
        return self.transcoder.transcode_file(input_file_path, output_file_path, profile, media_info, file_index, total_files_in_job)

    def attempt_repair_file(self, input_file_path: Path, output_file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Domyślna metoda naprawy, używająca profilu 'ffmpeg_copy' z parametrami kopiowania tagów.
        """
        logger.debug(f"FFmpegManager: Próba naprawy pliku (strategia domyślna 'ffmpeg_copy') dla '{input_file_path.name}'.")
        
        # Parametry dla domyślnej strategii "ffmpeg_copy" (z kopiowaniem tagów)
        default_ffmpeg_copy_params = ['-map_metadata', '0', '-map_chapters', '0', '-c', 'copy', '-map', '0', '-ignore_unknown', '-fflags', '+genpts']
        
        # Tworzymy tymczasowy obiekt RepairProfile dla tej operacji
        # copy_tags=False, ponieważ parametry mapowania są już w default_ffmpeg_copy_params
        temp_profile = RepairProfile(
            id=uuid.uuid4(), 
            name="Internal Default FFmpeg Copy",
            description="Wewnętrzna domyślna strategia kopiowania strumieni FFmpeg z zachowaniem tagów.",
            ffmpeg_params=default_ffmpeg_copy_params,
            applies_to_mkv_only=False, 
            copy_tags=False 
        )
        return self.execute_ffmpeg_repair_with_profile(input_file_path, output_file_path, temp_profile)


    def execute_ffmpeg_repair_with_profile(
        self,
        input_file_path: Path,
        output_file_path: Path,
        repair_profile: RepairProfile
    ) -> Tuple[bool, Optional[str]]:
        logger.info(f"Próba naprawy pliku '{input_file_path.name}' używając profilu naprawy FFmpeg: '{repair_profile.name}'")
        
        ffmpeg_exec_path = self.transcoder.ffmpeg_path 
        if not self.transcoder._verify_ffmpeg_executable():
            error_msg = f"FFmpeg ('{ffmpeg_exec_path}') niedostępny."
            logger.error(error_msg)
            return False, error_msg
        
        if not input_file_path.is_file():
            error_msg = f"Plik wejściowy '{input_file_path}' nie istnieje."
            logger.error(error_msg); return False, error_msg
        
        try:
            output_file_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            error_msg = f"Nie można utworzyć katalogu dla naprawionego pliku '{output_file_path.parent}': {e}"
            logger.error(error_msg, exc_info=True); return False, error_msg

        command = [ffmpeg_exec_path, '-y', '-nostdin', '-i', str(input_file_path)]
        
        final_params = list(repair_profile.ffmpeg_params) 

        # Jeśli profil ma włączone copy_tags, dodaj odpowiednie parametry,
        # o ile nie są już zdefiniowane przez użytkownika w profilu.
        if repair_profile.copy_tags:
            # Sprawdź, czy użytkownik nie dodał już -map_metadata lub -map_chapters
            has_manual_map_metadata = any(p.startswith('-map_metadata') for p in final_params)
            has_manual_map_chapters = any(p.startswith('-map_chapters') for p in final_params)
            
            params_to_prepend = []
            if not has_manual_map_metadata:
                params_to_prepend.extend(['-map_metadata', '0'])
            if not has_manual_map_chapters:
                params_to_prepend.extend(['-map_chapters', '0'])
            
            # Dodaj parametry na początku listy, aby dać im pierwszeństwo, 
            # ale po '-i input_file_path' i globalnych opcjach FFmpeg.
            # W tym przypadku, dodajemy je na początku final_params (które są po -i).
            if params_to_prepend:
                final_params = params_to_prepend + final_params
        
        command.extend(final_params)
        
        # Dodaj -loglevel error, jeśli nie ma go w profilu
        has_loglevel = False
        for i, param in enumerate(command):
            if param == '-loglevel':
                has_loglevel = True
                # Sprawdź, czy następny argument jest poprawnym poziomem logowania
                if i + 1 < len(command) and command[i+1] in ['quiet', 'panic', 'fatal', 'error', 'warning', 'info', 'verbose', 'debug', 'trace']:
                    break # Użytkownik zdefiniował, zostawiamy
                else: # Niepoprawny argument po -loglevel, lub brak argumentu - nadpiszemy
                    logger.warning(f"Profil '{repair_profile.name}' ma niekompletny parametr -loglevel. Nadpisywanie na 'error'.")
                    command[i+1] = 'error' # Spróbuj naprawić
                    break
            elif param.startswith('-loglevel='): # Obsługa formatu -loglevel=error
                has_loglevel = True; break
        
        if not has_loglevel:
            command.extend(['-loglevel', 'error'])
            
        command.append(str(output_file_path))

        logger.debug(f"Polecenie FFmpeg (profil naprawy '{repair_profile.name}'): {' '.join(command)}")
        
        repair_timeout_s = self.config_manager.get_config_value("processing", "repair_timeout_seconds", 300)
        effective_timeout = float(repair_timeout_s) if repair_timeout_s != 0 else None

        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=effective_timeout, check=False)
            
            if result.returncode == 0:
                logger.info(f"Naprawa pliku '{input_file_path.name}' profilem '{repair_profile.name}' zakończona pomyślnie (kod 0).")
                if result.stderr and result.stderr.strip(): 
                    logger.debug(f"FFmpeg stderr (profil '{repair_profile.name}'):\n{result.stderr.strip()}")
                return True, None
            else:
                error_msg_details = (f"FFmpeg (profil naprawy '{repair_profile.name}') zakończył z błędem (kod: {result.returncode}) dla pliku '{input_file_path.name}'.\n"
                                     f"Stderr: {result.stderr.strip() if result.stderr else 'Brak'}")
                logger.error(error_msg_details)
                if output_file_path.exists(): 
                    try: output_file_path.unlink(missing_ok=True)
                    except OSError as e_del: logger.warning(f"Nie można usunąć pliku wyjściowego '{output_file_path.name}' po nieudanej naprawie profilem: {e_del}")
                return False, f"Błąd FFmpeg (profil '{repair_profile.name}', kod: {result.returncode}). Szczegóły w logu."
        except subprocess.TimeoutExpired:
            error_msg = f"Przekroczono limit czasu ({effective_timeout}s) FFmpeg podczas naprawy profilem '{repair_profile.name}' dla pliku {input_file_path.name}."
            logger.error(error_msg, exc_info=True)
            if output_file_path.exists(): 
                try: output_file_path.unlink(missing_ok=True)
                except OSError as e_del: logger.warning(f"Nie można usunąć pliku wyjściowego '{output_file_path.name}' po timeoucie naprawy profilem: {e_del}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Nieoczekiwany błąd podczas naprawy pliku '{input_file_path.name}' profilem '{repair_profile.name}': {e}"
            logger.critical(error_msg, exc_info=True)
            if output_file_path.exists():
                try: 
                    output_file_path.unlink(missing_ok=True)
                except OSError as e_del: 
                    logger.warning(f"Nie można usunąć pliku wyjściowego '{output_file_path.name}' po nieoczekiwanym błędzie naprawy profilem: {e_del}")
            return False, error_msg

    def remux_file_with_mkvmerge(self, input_file_path: Path, output_file_path: Path) -> Tuple[bool, Optional[str]]:
        # ... (bez zmian od #69)
        logger.info(f"Próba remuksowania pliku '{input_file_path.name}' za pomocą mkvmerge do '{output_file_path.name}'.")
        if not self._verify_mkvmerge_executable(): error_msg = f"Narzędzie mkvmerge ('{self.mkvmerge_path}') jest niedostępne lub niepoprawnie skonfigurowane."; logger.error(error_msg); return False, error_msg
        if not input_file_path.is_file(): error_msg = f"Plik wejściowy do remuksowania '{input_file_path}' nie istnieje."; logger.error(error_msg); return False, error_msg
        if input_file_path.suffix.lower() != ".mkv": error_msg = f"Strategia mkvmerge_remux jest przeznaczona tylko dla plików .mkv. Plik: '{input_file_path.name}'."; logger.warning(error_msg); return False, error_msg
        try: output_file_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e: error_msg = f"Nie można utworzyć katalogu dla zremuksowanego pliku '{output_file_path.parent}': {e}"; logger.error(error_msg, exc_info=True); return False, error_msg
        command = [self.mkvmerge_path, '--output', str(output_file_path), str(input_file_path)]; logger.debug(f"Polecenie mkvmerge: {' '.join(command)}")
        repair_timeout_s = self.config_manager.get_config_value("processing", "repair_timeout_seconds", 300); effective_timeout = float(repair_timeout_s) if repair_timeout_s != 0 else None
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=effective_timeout, check=False)
            if result.returncode == 0: 
                logger.info(f"Remuksowanie pliku '{input_file_path.name}' przez mkvmerge zakończone pomyślnie (kod 0).")
                if result.stdout and result.stdout.strip(): logger.debug(f"mkvmerge stdout: {result.stdout.strip()}")
                if result.stderr and result.stderr.strip(): logger.debug(f"mkvmerge stderr: {result.stderr.strip()}")
                return True, None
            elif result.returncode == 1: 
                logger.warning(f"Remuksowanie pliku '{input_file_path.name}' przez mkvmerge zakończone z OSTRZEŻENIAMI (kod 1). Plik może być użyteczny.")
                logger.warning(f"mkvmerge stdout: {result.stdout.strip() if result.stdout else 'Brak'}"); logger.warning(f"mkvmerge stderr: {result.stderr.strip() if result.stderr else 'Brak'}")
                return True, "mkvmerge zgłosił ostrzeżenia (szczegóły w logu)."
            else: 
                error_msg_details = (f"mkvmerge zakończył z błędem (kod: {result.returncode}) dla pliku '{input_file_path.name}'.\nStdout: {result.stdout.strip() if result.stdout else 'Brak'}\nStderr: {result.stderr.strip() if result.stderr else 'Brak'}"); logger.error(error_msg_details)
                if output_file_path.exists():
                    try: output_file_path.unlink(missing_ok=True)
                    except OSError as e_del: logger.warning(f"Nie można usunąć pliku wyjściowego '{output_file_path.name}' po nieudanym remuksowaniu mkvmerge: {e_del}")
                return False, f"Błąd mkvmerge (kod: {result.returncode}). Szczegóły w logu."
        except subprocess.TimeoutExpired:
            error_msg = f"Przekroczono limit czasu ({effective_timeout}s) mkvmerge podczas remuksowania {input_file_path.name}."; logger.error(error_msg, exc_info=True)
            if output_file_path.exists(): 
                try: output_file_path.unlink(missing_ok=True)
                except OSError as e_del: logger.warning(f"Nie można usunąć pliku wyjściowego '{output_file_path.name}' po timeoucie mkvmerge: {e_del}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Nieoczekiwany błąd podczas remuksowania pliku '{input_file_path.name}' przez mkvmerge: {e}"; logger.critical(error_msg, exc_info=True)
            if output_file_path.exists(): 
                try: output_file_path.unlink(missing_ok=True)
                except OSError as e_del: logger.warning(f"Nie można usunąć pliku wyjściowego '{output_file_path.name}' po nieoczekiwanym błędzie mkvmerge: {e_del}")
            return False, error_msg

    def is_file_readable_by_ffprobe(self, file_path: Path) -> bool:
        logger.debug(f"FFmpegManager: Sprawdzanie czytelności pliku '{file_path.name}' przez FFprobe.")
        return self.probe_extractor.is_file_readable_by_ffprobe(file_path)

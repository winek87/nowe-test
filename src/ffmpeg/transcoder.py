# src/ffmpeg/transcoder.py
import subprocess
import logging
import re
import time
from pathlib import Path
from typing import List, Optional, Callable, Tuple, Dict, Any
import threading

from ..config_manager import ConfigManager
from ..models import EncodingProfile, MediaInfo

logger = logging.getLogger(__name__)

ProgressCallbackType = Callable[
    [
        float, Optional[float], str, Optional[int], Optional[int],
        Optional[float], Optional[str], Optional[str], Optional[float],
        Optional[str], Optional[str]
    ], None
]

class Transcoder:
    def __init__(self, config_manager: ConfigManager, display_progress_callback: Optional[ProgressCallbackType] = None):
        self.config_manager = config_manager
        ffmpeg_path_config = self.config_manager.get_config_value('ffmpeg', 'ffmpeg_path', 'ffmpeg')
        if isinstance(ffmpeg_path_config, Path):
            self.ffmpeg_path = str(ffmpeg_path_config.resolve())
        else:
            self.ffmpeg_path = str(ffmpeg_path_config)
        self.display_progress_callback = display_progress_callback
        logger.debug(f"Transcoder zainicjalizowany. Ścieżka FFmpeg: {self.ffmpeg_path}.")

    def _verify_ffmpeg_executable(self) -> bool:
        # ... (bez zmian)
        try:
            process = subprocess.Popen([self.ffmpeg_path, '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
            stdout, stderr = process.communicate(timeout=5)
            if process.returncode == 0: logger.debug(f"FFmpeg zweryfikowany pomyślnie: {self.ffmpeg_path}"); return True
            else: logger.error(f"FFmpeg nie powiódł się przy weryfikacji (kod: {process.returncode}). Ścieżka: {self.ffmpeg_path}. Stderr: {stderr.strip()}"); return False
        except FileNotFoundError: logger.error(f"Plik wykonywalny FFmpeg nie znaleziony: {self.ffmpeg_path}."); return False
        except subprocess.TimeoutExpired: logger.error(f"Timeout podczas weryfikacji FFmpeg: {self.ffmpeg_path}"); return False
        except Exception as e: logger.error(f"Nieoczekiwany błąd weryfikacji FFmpeg ({self.ffmpeg_path}): {e}", exc_info=True); return False

    def transcode_file(self,
                       input_file_path: Path,
                       output_file_path: Path,
                       profile: EncodingProfile,
                       media_info: MediaInfo,
                       file_index: Optional[int] = None,
                       total_files_in_job: Optional[int] = None
                       ) -> Tuple[bool, Optional[str]]:

        file_label = f"'{input_file_path.name}'"
        if file_index is not None and total_files_in_job is not None:
            file_label += f" (plik {file_index}/{total_files_in_job})"
        logger.info(f"Rozpoczynanie transkodowania dla {file_label} do '{output_file_path.name}'. Profil: '{profile.name}'.")

        if not self._verify_ffmpeg_executable(): error_msg = f"FFmpeg ('{self.ffmpeg_path}') niedostępny."; logger.error(error_msg); return False, error_msg
        if not input_file_path.is_file(): error_msg = f"Plik wejściowy {file_label} ('{input_file_path}') nie istnieje."; logger.error(error_msg); return False, error_msg
        try: output_file_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e: error_msg = f"Nie można utworzyć katalogu '{output_file_path.parent}' dla {file_label}: {e}"; logger.error(error_msg, exc_info=True); return False, error_msg

        command = [self.ffmpeg_path, '-y', '-nostdin', '-i', str(input_file_path)]
        # TEST: Tymczasowe usunięcie '-progress', 'pipe:1'
        # command.extend(['-progress', 'pipe:1']) 
        command.extend(profile.ffmpeg_params)
        command.append(str(output_file_path))
        logger.info(f"Polecenie FFmpeg dla {file_label}: {' '.join(command)}")

        process = None
        start_wall_time = time.time()
        ffmpeg_full_output_log: List[str] = []
        current_fps: Optional[float] = None; current_speed: Optional[str] = None; current_bitrate: Optional[str] = None; current_output_size_str: Optional[str] = None

        try:
            logger.debug(f"Uruchamianie procesu Popen dla {file_label}...")
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', bufsize=1, universal_newlines=True)
            logger.info(f"Proces Popen dla {file_label} uruchomiony (PID: {process.pid}).")

            def stream_reader(pipe: Optional[Any], pipe_name: str, is_stdout_for_progress: bool = False):
                nonlocal current_fps, current_speed, current_bitrate, current_output_size_str
                logger.info(f"Wątek czytający {pipe_name} dla {file_label} wystartował.")
                try:
                    if pipe:
                        for line_number, line in enumerate(iter(pipe.readline, '')):
                            line_stripped = line.strip()
                            if line_stripped:
                                ffmpeg_full_output_log.append(f"FFmpeg_{pipe_name}_{line_number}: {line_stripped}")
                                if logger.isEnabledFor(logging.DEBUG): # Zawsze loguj stderr na DEBUG
                                     logger.debug(f"FFmpeg_{pipe_name} ({file_label}) LINE {line_number}: {line_stripped}")

                                # Jeśli to stdout i mieliśmy -progress pipe:1 (teraz zakomentowane)
                                if is_stdout_for_progress:
                                    if "out_time_ms=" in line_stripped:
                                        try:
                                            current_time_us_str = line_stripped.split('=')[1]
                                            current_time_us = int(current_time_us_str)
                                            current_processed_duration_s = current_time_us / 1_000_000.0
                                            percentage = 0.0; eta_file_s: Optional[float] = None
                                            if media_info and media_info.duration and media_info.duration > 0:
                                                total_duration_s = media_info.duration
                                                percentage = (current_processed_duration_s / total_duration_s) * 100
                                                percentage = min(100.0, max(0.0, percentage))
                                                elapsed_wall_time = time.time() - start_wall_time
                                                if current_processed_duration_s > 0 and elapsed_wall_time > 0.1:
                                                    media_seconds_per_wall_second = current_processed_duration_s / elapsed_wall_time
                                                    if media_seconds_per_wall_second > 0:
                                                        remaining_media_seconds = total_duration_s - current_processed_duration_s
                                                        if remaining_media_seconds > 0: eta_file_s = remaining_media_seconds / media_seconds_per_wall_second
                                            elapsed_wall_time = time.time() - start_wall_time
                                            if self.display_progress_callback:
                                                self.display_progress_callback(percentage, elapsed_wall_time, input_file_path.name, file_index, total_files_in_job, current_fps, current_speed, current_bitrate, eta_file_s, current_output_size_str, str(output_file_path))
                                        except ValueError: logger.warning(f"Nie można sparsować czasu postępu z linii: {line_stripped}")
                                        except Exception as e_prog: logger.error(f"Błąd przetwarzania postępu FFmpeg (czas): {e_prog}", exc_info=True)
                                    
                                    # Poniższe parsowanie z stderr jest teraz mniej relewantne, jeśli -progress pipe:1 jest wyłączone
                                    # ale zostawiam na wypadek, gdyby stderr zawierało te informacje przy innych ustawieniach loglevel
                                    fps_match = re.search(r"fps=\s*([\d\.]+)", line_stripped); current_fps = float(fps_match.group(1)) if fps_match else current_fps
                                    speed_match = re.search(r"speed=\s*([\d\.]+)x", line_stripped); current_speed = f"{speed_match.group(1)}x" if speed_match else current_speed
                                    if not current_speed: speed_match_alt = re.search(r"speed=\s*(\S+)", line_stripped); current_speed = speed_match_alt.group(1) if speed_match_alt else current_speed
                                    bitrate_match = re.search(r"bitrate=\s*([\d\.]+)\s*kbits/s", line_stripped); current_bitrate = f"{bitrate_match.group(1)}kbps" if bitrate_match else current_bitrate
                                    if not current_bitrate: bitrate_match_alt = re.search(r"bitrate=\s*(\S+)", line_stripped); current_bitrate = bitrate_match_alt.group(1) if bitrate_match_alt and "N/A" not in bitrate_match_alt.group(1).upper() else current_bitrate
                                    size_match = re.search(r"\ssize=\s*(\S+)", line_stripped); current_output_size_str = size_match.group(1).strip() if size_match else current_output_size_str
                        logger.info(f"Wątek czytający {pipe_name} dla {file_label} zakończył pętlę iteracji.")
                    else: logger.warning(f"Potok (pipe) dla {pipe_name} ({file_label}) jest None.")
                except Exception as e_thread: logger.error(f"Błąd krytyczny w wątku czytającym {pipe_name} dla {file_label}: {e_thread}", exc_info=True)
                finally:
                    if pipe: pipe.close()
                    logger.info(f"Wątek czytający {pipe_name} dla {file_label} zakończony (blok finally).")

            # Jeśli -progress pipe:1 jest wyłączone, stdout_thread nie będzie dostarczał danych postępu
            stdout_thread = None
            if process.stdout:
                 # Jeśli chcemy nadal czytać stdout (np. dla 'progress=end'), ustaw is_stdout_for_progress=True
                 # Ale bez -progress pipe:1, nie będzie tam danych postępu.
                 # Jeśli -progress jest zakomentowane, to stdout będzie pusty lub będzie zawierał inne dane (zależnie od -loglevel)
                stdout_thread = threading.Thread(target=stream_reader, args=(process.stdout, "stdout", False)) # Zmieniono na False
                stdout_thread.start()
            if process.stderr:
                stderr_thread = threading.Thread(target=stream_reader, args=(process.stderr, "stderr", False))
                stderr_thread.start()
            
            # Timeout calculation
            enable_dynamic_timeout = self.config_manager.get_config_value('ffmpeg', 'enable_dynamic_timeout', True)
            process_timeout: Optional[float] = None
            if enable_dynamic_timeout and media_info and media_info.duration and media_info.duration > 0:
                multiplier = self.config_manager.get_config_value('ffmpeg', 'dynamic_timeout_multiplier', 2.0)
                buffer_s = self.config_manager.get_config_value('ffmpeg', 'dynamic_timeout_buffer_seconds', 300)
                min_s = self.config_manager.get_config_value('ffmpeg', 'dynamic_timeout_min_seconds', 600)
                calculated_timeout = (media_info.duration * multiplier) + buffer_s
                process_timeout = max(min_s, calculated_timeout)
                logger.info(f"Timeout FFmpeg dla {file_label} (dynamiczny): {process_timeout:.1f}s (Dur: {media_info.duration:.0f}s * {multiplier:.1f} + {buffer_s}s, Min: {min_s}s)")
            else:
                fixed_timeout_s = self.config_manager.get_config_value('ffmpeg', 'fixed_timeout_seconds', 86400)
                if fixed_timeout_s > 0: process_timeout = float(fixed_timeout_s)
                logger.info(f"Timeout FFmpeg dla {file_label} (stały lub brak trwania): {process_timeout if process_timeout is not None else 'Brak'}s")

            # Czekanie na wątki i proces
            if stdout_thread: stdout_thread.join(timeout=process_timeout + 60 if process_timeout else None) # Dłuższy timeout dla wątków
            if stderr_thread: stderr_thread.join(timeout=15) # stderr powinien zakończyć się szybciej

            final_return_code = None
            if process: # Upewnij się, że proces został utworzony
                if process.poll() is None: # Jeśli proces wciąż działa, spróbuj wait z timeoutem
                    logger.info(f"Proces FFmpeg dla {file_label} wciąż działa, oczekiwanie z timeoutem...")
                    try:
                        final_return_code = process.wait(timeout=10) # Krótki dodatkowy timeout na zakończenie
                    except subprocess.TimeoutExpired:
                        logger.error(f"Proces FFmpeg dla {file_label} nie zakończył się w dodatkowym czasie. Zabijanie.")
                        process.kill()
                        final_return_code = process.wait() # Pobierz kod po zabiciu
                        error_msg_for_user = f"Proces FFmpeg przekroczył całkowity limit czasu i został zabity dla {file_label}."
                        return False, error_msg_for_user
                else: # Proces już się zakończył
                    final_return_code = process.returncode
            
            logger.info(f"Proces FFmpeg dla {file_label} zakończony z kodem: {final_return_code}.")
            full_log_str = "\n".join(ffmpeg_full_output_log)

            if final_return_code == 0:
                logger.info(f"Transkodowanie {file_label} zakończone pomyślnie (kod 0).")
                if self.display_progress_callback:
                     elapsed_wall_time = time.time() - start_wall_time
                     final_size_match = re.search(r"Lsize=\s*(\S+)", full_log_str, re.IGNORECASE) # Spróbuj znaleźć Lsize w stderr
                     final_output_size = final_size_match.group(1) if final_size_match else current_output_size_str
                     self.display_progress_callback(100.0, elapsed_wall_time, input_file_path.name, file_index, total_files_in_job, current_fps, current_speed, current_bitrate, 0.0, final_output_size, str(output_file_path))
                if logger.isEnabledFor(logging.DEBUG) and full_log_str: logger.debug(f"Pełny log FFmpeg (stderr) dla {file_label}:\n{full_log_str}")
                return True, None
            else:
                error_msg_for_user = f"Błąd FFmpeg (kod: {final_return_code}) dla {file_label}. Szczegóły w pliku app.log."
                logger.error(f"FFmpeg zakończył z kodem błędu {final_return_code} dla {file_label}. Pełny log FFmpeg (stderr):\n{full_log_str}")
                return False, error_msg_for_user

        except subprocess.TimeoutExpired: # Ten timeout jest z Popen.communicate lub process.wait()
            error_msg = f"Przekroczono główny limit czasu operacji FFmpeg podczas transkodowania {file_label}."
            logger.error(error_msg, exc_info=True)
            if process and process.poll() is None: process.kill(); process.wait()
            return False, error_msg
        except FileNotFoundError:
            error_msg = f"Plik wykonywalny FFmpeg nie znaleziony: {self.ffmpeg_path} dla {file_label}."
            logger.critical(error_msg, exc_info=True); return False, error_msg
        except Exception as e:
            error_msg = f"Nieoczekiwany błąd podczas transkodowania {file_label}: {e}"
            logger.critical(error_msg, exc_info=True)
            if process and process.poll() is None: process.kill(); process.wait()
            return False, error_msg
        finally:
            if stdout_thread and stdout_thread.is_alive(): stdout_thread.join(timeout=2)
            if stderr_thread and stderr_thread.is_alive(): stderr_thread.join(timeout=2)
            if self.display_progress_callback:
                if hasattr(self.display_progress_callback, '__self__'):
                    callback_object = getattr(self.display_progress_callback, '__self__', None)
                    if callback_object and hasattr(callback_object, '_displaying_progress'):
                        setattr(callback_object, '_displaying_progress', False)

    def attempt_repair_file(self, input_file_path: Path, output_file_path: Path) -> Tuple[bool, Optional[str]]:
        # ... (bez zmian od #69) ...
        logger.debug(f"Próba naprawy pliku '{input_file_path.name}' do '{output_file_path.name}'.")
        if not self._verify_ffmpeg_executable(): error_msg = f"FFmpeg ('{self.ffmpeg_path}') niedostępny."; logger.error(error_msg); return False, error_msg
        if not input_file_path.is_file(): error_msg = f"Plik wejściowy do naprawy '{input_file_path}' nie istnieje."; logger.error(error_msg); return False, error_msg
        try: output_file_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e: error_msg = f"Nie można utworzyć katalogu dla naprawionego pliku '{output_file_path.parent}': {e}"; logger.error(error_msg, exc_info=True); return False, error_msg
        command = [self.ffmpeg_path, '-y', '-nostdin', '-i', str(input_file_path), '-c', 'copy', '-loglevel', 'error', str(output_file_path)]
        logger.debug(f"Polecenie FFmpeg (naprawa): {' '.join(command)}")
        try:
            repair_timeout_cfg = self.config_manager.get_config_value("processing", "repair_timeout_seconds", 300)
            repair_timeout = float(repair_timeout_cfg) if repair_timeout_cfg > 0 else None

            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=repair_timeout, check=False)
            if result.returncode == 0:
                if result.stdout and result.stdout.strip(): logger.debug(f"FFmpeg repair stdout dla '{input_file_path.name}':\n{result.stdout.strip()}")
                if result.stderr and result.stderr.strip(): logger.warning(f"FFmpeg repair stderr (mimo -loglevel error) dla '{input_file_path.name}':\n{result.stderr.strip()}")
                logger.info(f"Naprawa pliku '{input_file_path.name}' zakończona (kod 0). Wynik w '{output_file_path.name}'.")
                if output_file_path.exists() and output_file_path.stat().st_size > 0: return True, None
                else:
                    err_msg = f"Naprawa pliku '{input_file_path.name}' technicznie zakończona sukcesem (kod 0), ale plik wyjściowy jest pusty lub nie istnieje."
                    logger.error(err_msg)
                    if output_file_path.exists():
                        try: output_file_path.unlink(missing_ok=True)
                        except OSError as e_del: logger.warning(f"Nie można usunąć pustego pliku wyjściowego po nieudanej naprawie: {e_del}")
                    return False, err_msg
            else:
                error_msg_details = (f"FFmpeg (naprawa) zakończył z kodem błędu {result.returncode} dla pliku '{input_file_path.name}'.\nStdout: {result.stdout.strip() if result.stdout else 'Brak'}\nStderr: {result.stderr.strip() if result.stderr else 'Brak'}"); logger.error(error_msg_details)
                if output_file_path.exists():
                    try: output_file_path.unlink(missing_ok=True)
                    except OSError as e_del: logger.warning(f"Nie można usunąć pliku wyjściowego po nieudanej naprawie: {e_del}")
                return False, f"Błąd naprawy FFmpeg (kod: {result.returncode}). Szczegóły w logu."
        except subprocess.TimeoutExpired:
            error_msg = f"Przekroczono limit czasu ({repair_timeout}s) FFmpeg podczas naprawy {input_file_path.name}."
            logger.error(error_msg, exc_info=True)
            if output_file_path.exists():
                try: output_file_path.unlink(missing_ok=True)
                except OSError as e_del: logger.warning(f"Nie można usunąć pliku wyjściowego po timeoucie naprawy: {e_del}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Nieoczekiwany błąd podczas próby naprawy pliku '{input_file_path.name}' przez FFmpeg: {e}"
            logger.critical(error_msg, exc_info=True)
            if output_file_path.exists():
                try: output_file_path.unlink(missing_ok=True)
                except OSError as e_del: logger.warning(f"Nie można usunąć pliku wyjściowego po nieoczekiwanym błędzie naprawy: {e_del}")
            return False, error_msg

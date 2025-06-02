# src/cli_handlers/job_handler.py
import logging
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Callable # Dodano Callable
import platform
import time
import re
import json # Dodano dla _display_pre_job_summary (jeśli Panel nie jest używany)

from ..cli_display import CLIDisplay, MenuOption, READCHAR_AVAILABLE as DISPLAY_READCHAR_AVAILABLE
from ..config_manager import ConfigManager
from ..models import JobState, ProcessedFile, EncodingProfile, MediaInfo
from ..profiler import Profiler
from ..ffmpeg.ffmpeg_manager import FFmpegManager
from ..filesystem.path_resolver import PathResolver
from ..filesystem.job_state_manager import JobStateManager
from ..filesystem.directory_scanner import DirectoryScanner, ScanProgressCallback
from ..filesystem.damaged_files_manager import DamagedFilesManager
from ..system_monitor.resource_monitor import ResourceMonitor
from .. import cli_styles as styles

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.padding import Padding # Dodano Padding dla Rich
    RICH_FOR_JOB_HANDLER_AVAILABLE = True
except ImportError:
    Console, Panel, Text, Padding = None, None, None, None # type: ignore
    RICH_FOR_JOB_HANDLER_AVAILABLE = False

logger = logging.getLogger(__name__)

class JobCLIHandler:
    def __init__(self,
                 display: CLIDisplay,
                 config_manager: ConfigManager,
                 profiler: Profiler,
                 ffmpeg_manager: FFmpegManager,
                 path_resolver: PathResolver,
                 job_state_manager: JobStateManager,
                 directory_scanner: DirectoryScanner,
                 damaged_files_manager: DamagedFilesManager,
                 resource_monitor: ResourceMonitor):
        logger.debug("JobCLIHandler: Inicjalizacja rozpoczęta.")
        self.display = display; self.config_manager = config_manager; self.profiler = profiler
        self.ffmpeg_manager = ffmpeg_manager; self.path_resolver = path_resolver
        self.job_state_manager = job_state_manager; self.directory_scanner = directory_scanner
        self.damaged_files_manager = damaged_files_manager; self.resource_monitor = resource_monitor
        self.current_job_state: Optional[JobState] = None; self.is_processing: bool = False
        self._last_selected_profile_idx = 0 
        
        if RICH_FOR_JOB_HANDLER_AVAILABLE and Console is not None:
            self.rich_console = Console()
        else:
            self.rich_console = None
            
        logger.debug("JobCLIHandler: Inicjalizacja zakończona.")

    @staticmethod
    def _infer_codec_from_params(params: List[str], stream_type: str) -> Optional[str]:
        codec_param_short = f"-c:{stream_type}"; codec_param_long = f"-codec:{stream_type}"
        for i, param in enumerate(params):
            if param == codec_param_short or param == codec_param_long:
                if i + 1 < len(params) and not params[i+1].startswith('-'): return params[i+1]
        return None

    @staticmethod
    def _infer_target_bitrate_from_params(params: List[str], stream_type: str) -> Optional[int]:
        bitrate_param = f"-b:{stream_type}"
        for i, param in enumerate(params):
            if param == bitrate_param:
                if i + 1 < len(params):
                    val_str = params[i+1].lower();
                    try:
                        num_val_str = val_str; multiplier = 1
                        if val_str.endswith('k'): num_val_str = val_str[:-1]; multiplier = 1000
                        elif val_str.endswith('m'): num_val_str = val_str[:-1]; multiplier = 1000000
                        return int(float(num_val_str) * multiplier)
                    except ValueError: logger.warning(f"Nie można sparsować wartości bitrate: '{params[i+1]}' dla strumienia '{stream_type}'"); return None
        return None

    def _select_profile(self) -> Optional[EncodingProfile]:
        available_profiles = self.profiler.get_all_profiles()
        if not available_profiles: 
            self.display.display_warning("Brak dostępnych profili kodowania. Utwórz profil w opcjach (4).")
            return None
        
        self.display.clear_screen()
        self.display.display_header("Wybierz Profil Kodowania")
        
        menu_options: List[MenuOption] = []
        profile_map: Dict[str, EncodingProfile] = {} 

        for i, profile in enumerate(available_profiles):
            desc_short = profile.description[:50] + '...' if len(profile.description) > 50 else profile.description
            menu_key = str(i + 1) 
            menu_options.append((menu_key, f"{profile.name} ({desc_short})", styles.ICON_PROFILE))
            profile_map[menu_key] = profile # Używamy numeru jako klucza
        
        menu_options.append(("q", "Anuluj wybór", styles.ICON_EXIT))

        initial_idx = self._last_selected_profile_idx
        if not (0 <= initial_idx < len(available_profiles)):
            initial_idx = 0

        # Poprawiona obsługa zwracanej wartości z present_interactive_menu
        choice_tuple = self.display.present_interactive_menu(
             header_text="Wybierz Profil Kodowania", 
             menu_options=menu_options, 
             prompt_message="Wybierz profil strzałkami (↑↓), Enter, lub wpisz numer/literę:",
             initial_selection_index=initial_idx,
             allow_numeric_select=True 
        )
        selected_key = choice_tuple[0] if isinstance(choice_tuple, tuple) else choice_tuple
        selected_idx_in_menu = choice_tuple[1] if isinstance(choice_tuple, tuple) else -1 # Indeks w menu_options

        if selected_key is None or selected_key.lower() == 'q': 
            self.display.display_info("Wybór profilu anulowany.")
            return None
        
        # Sprawdź, czy wybrany klucz jest w naszej mapie (czyli jest numerem profilu)
        if selected_key in profile_map:
            selected_profile = profile_map[selected_key]
            self.display.display_success(f"Wybrano profil: {selected_profile.name}")
            # Znajdź rzeczywisty indeks profilu na liście available_profiles
            # na podstawie wybranego klucza numerycznego
            try:
                actual_profile_index = int(selected_key) - 1
                if 0 <= actual_profile_index < len(available_profiles):
                    self._last_selected_profile_idx = actual_profile_index
            except ValueError:
                pass # Jeśli selected_key nie jest liczbą, nie aktualizuj indeksu
            return selected_profile
        else:
            self.display.display_warning("Nieprawidłowy wybór profilu.")
            self.display.press_enter_to_continue()
            return self._select_profile()


    def _build_file_info_text(self, title: str, file_path: Path, media_info: Optional[MediaInfo],
                               output_path: Optional[Path] = None, profile: Optional[EncodingProfile] = None, include_input_header: bool = True) -> str:
        # ... (bez zmian od #66)
        lines = [];
        if title: lines.append(title)
        if include_input_header: lines.append(f"{styles.STYLE_INFO}--- Szczegóły pliku wejściowego ---{styles.ANSI_RESET}")
        lines.append(f"  Nazwa: {file_path.name}")
        if media_info:
            if media_info.format_name: lines.append(f"  Format: {media_info.format_name}")
            if media_info.duration: lines.append(f"  Czas trwania: {self.display.formatter.format_progress_time(media_info.duration)}")
            if media_info.bit_rate: lines.append(f"  Bitrate (całk.): {self.display.formatter.format_bitrate(str(media_info.bit_rate / 1000.0) + 'kbps') if media_info.bit_rate else 'N/A'}")
            if media_info.width and media_info.height: lines.append(f"  Rozdzielczość: {media_info.width}x{media_info.height}")
            if media_info.frame_rate: lines.append(f"  Klatki/s: {media_info.frame_rate}")
            if media_info.video_codec: lines.append(f"  Kodek wideo (wej.): {media_info.video_codec}")
            if media_info.audio_codec: lines.append(f"  Kodek audio (wej.): {media_info.audio_codec}")
            try: file_size_bytes = file_path.stat().st_size; lines.append(f"  Rozmiar pliku (wej.): {self.display.formatter.format_filesize(str(file_size_bytes) + 'B')}")
            except FileNotFoundError: lines.append(f"  {styles.ICON_WARNING} Nie można odczytać rozmiaru pliku źródłowego.")
        if output_path and profile:
            lines.append(f"{styles.STYLE_INFO}\n--- Planowane wyjście ---{styles.ANSI_RESET}")
            lines.append(f"  Nazwa: {output_path.name}"); lines.append(f"  Format wyjściowy: .{profile.output_extension}")
            target_vcodec = self._infer_codec_from_params(profile.ffmpeg_params, 'v'); target_acodec = self._infer_codec_from_params(profile.ffmpeg_params, 'a')
            lines.append(f"  Planowany kodek wideo: {target_vcodec if target_vcodec else '(wg parametrów FFmpeg)'}"); lines.append(f"  Planowany kodek audio: {target_acodec if target_acodec else '(wg parametrów FFmpeg)'}")
            estimated_size_bytes: Optional[int] = None; estimation_note = "(N/A - brak stałego bitrate wideo w profilu / CRF lub czasu trwania)"
            if media_info and media_info.duration and media_info.duration > 0:
                video_b_bps = self._infer_target_bitrate_from_params(profile.ffmpeg_params, 'v')
                if video_b_bps is not None and video_b_bps > 0:
                    audio_b_bps = self._infer_target_bitrate_from_params(profile.ffmpeg_params, 'a'); total_target_bps = video_b_bps + (audio_b_bps or 0); estimated_size_bytes = int((total_target_bps / 8.0) * media_info.duration); estimation_note = "(na podst. bitrate wideo i ew. audio w profilu)"
            if estimated_size_bytes is not None: lines.append(f"  Szacowany rozmiar wyj.: {self.display.formatter.format_filesize(str(estimated_size_bytes) + 'B')} {estimation_note}")
            else: lines.append(f"  Szacowany rozmiar wyj.: {estimation_note}")
            lines.append(f"    Do katalogu: {output_path.parent}")
        return "\n".join(lines)

    def _display_pre_job_summary(self, job: JobState, first_file_info: Optional[ProcessedFile], first_output_path: Path, selected_profile: EncodingProfile):
        # ... (bez zmian od #66)
        self.display.clear_screen(); self.display.display_message("--- Podsumowanie Zadania ---", style=styles.STYLE_HEADER)
        sys_info_lines = [f"System: {platform.system()} {platform.release()} ({platform.machine()})"]
        if self.resource_monitor.is_available():
            cpu_stats = self.resource_monitor.get_cpu_stats();
            if cpu_stats: sys_info_lines.append(f" {styles.ICON_CPU} CPU: Log: {cpu_stats.get('liczba_rdzeni_logicznych', 'N/A')}, Fiz: {cpu_stats.get('liczba_rdzeni_fizycznych', 'N/A')}")
            ram_usage = self.resource_monitor.get_ram_usage();
            if ram_usage: sys_info_lines.append(f" {styles.ICON_RAM} RAM: {ram_usage['total_gb']:.1f} GB całkowitej")
            target_disk_path = first_output_path.parent; disk_usage = self.resource_monitor.get_specific_disk_usage(target_disk_path)
            if disk_usage: sys_info_lines.append(f" {styles.ICON_DISK} Dysk docelowy ({target_disk_path}): Wolne {disk_usage['free_gb']:.1f}GB z {disk_usage['total_gb']:.1f}GB ({disk_usage['percent_used']:.1f}% zajęte)")
            else: sys_info_lines.append(f" {styles.ICON_DISK} {styles.STYLE_WARNING}Nie można uzyskać informacji o wolnym miejscu dla dysku: {target_disk_path}{styles.ANSI_RESET}")
        job_summary_lines = [f"{styles.ICON_FOLDER_SCAN} Katalog źródłowy: {job.source_directory.resolve()}", f"{styles.ICON_LIST} Liczba plików do przetworzenia: {job.total_files}", f"{styles.ICON_PROFILE} Wybrany profil: {selected_profile.name}"]
        if self.rich_console and Panel and Text and Padding:
            sys_text = Text.from_ansi("\n".join(sys_info_lines)); self.rich_console.print(Panel(Padding(sys_text, (0,1)), title="Informacje o Systemie i Zasobach", border_style="blue", expand=False))
            job_text = Text.from_ansi("\n".join(job_summary_lines)); self.rich_console.print(Panel(Padding(job_text, (0,1)), title="Ogólne Informacje o Zadaniu", border_style="blue", expand=False))
        else: 
            for line in sys_info_lines: self.display.display_info(line)
            self.display.display_separator(length=40);
            for line in job_summary_lines: self.display.display_info(line)
        if first_file_info:
            panel_title_first_file = f"{styles.ICON_PLAY} Pierwszy plik w kolejce: {first_file_info.original_path.name}"; content_text_first_file = self._build_file_info_text(title="", file_path=first_file_info.original_path, media_info=first_file_info.media_info, output_path=first_output_path, profile=selected_profile, include_input_header=False)
            if self.rich_console and Panel and Text and Padding:
                panel_content_file = Text.from_ansi(content_text_first_file.strip()); clean_panel_title = re.sub(r'\x1b\[[0-9;]*m', '', panel_title_first_file); self.rich_console.print(Panel(Padding(panel_content_file, (0,1)), title=clean_panel_title, border_style="green", expand=False))
            else: 
                self.display.display_message(f"\n{panel_title_first_file}", style=styles.STYLE_HEADER); plain_content_for_fallback = re.sub(r'\x1b\[[0-9;]*m', '', content_text_first_file)
                for line in plain_content_for_fallback.strip().split('\n'):
                    if line.strip(): self.display.display_info(f"  {line.strip()}")
        self.display.display_separator()

    def start_new_directory_scan_job_cli(self):
        # ... (logika jak w #66, ale używa poprawionego _select_profile)
        logger.debug("start_new_directory_scan_job_cli rozpoczęte.")
        if self.is_processing: self.display.display_warning("Inne zadanie jest aktualnie w toku."); self.display.press_enter_to_continue(); return
        self.display.clear_screen(); self.display.display_header(f"{styles.ICON_PLAY} Nowe zadanie transkodowania (Skanowanie folderu)")
        last_used_dir_path_obj = self.config_manager.get_config_value('paths', 'last_used_source_directory'); last_used_dir_str = str(last_used_dir_path_obj.resolve()) if isinstance(last_used_dir_path_obj, Path) else ""
        prompt_message = "Podaj ścieżkę do katalogu źródłowego"; prompt_message += f" [ostatnio: {last_used_dir_str}]: " if last_used_dir_str else ": "
        source_dir_path_str = self.display.get_user_choice(prompt_message); final_source_dir_path: Optional[Path] = None
        if not source_dir_path_str and last_used_dir_path_obj and last_used_dir_path_obj.is_dir(): final_source_dir_path = last_used_dir_path_obj; self.display.display_info(f"Używanie ostatnio wybranego katalogu: {final_source_dir_path.resolve()}")
        elif source_dir_path_str:
            path_candidate = Path(source_dir_path_str).expanduser().resolve()
            if path_candidate.is_dir(): final_source_dir_path = path_candidate
            else: self.display.display_error(f"Podana ścieżka nie jest prawidłowym katalogiem: {path_candidate}"); self.display.press_enter_to_continue(); return
        else: self.display.display_error("Nie podano ścieżki do katalogu."); self.display.press_enter_to_continue(); return
        if not final_source_dir_path: self.display.display_error("Nie udało się ustalić katalogu źródłowego."); self.display.press_enter_to_continue(); return
        self.config_manager.set_config_value('paths', 'last_used_source_directory', str(final_source_dir_path))
        selected_profile = self._select_profile()
        if not selected_profile: self.display.press_enter_to_continue(); return
        job_id = uuid.uuid4(); self.current_job_state = JobState(job_id=job_id, source_directory=final_source_dir_path, selected_profile_id=selected_profile.id, status="Skanowanie", start_time=datetime.now(), processed_files=[], total_files=0); self.job_state_manager.save_job_state(self.current_job_state)
        self.display.display_info(f"Skanowanie katalogu '{final_source_dir_path.resolve()}'...")
        self.directory_scanner.scan_directory_and_populate_job_state(self.current_job_state, progress_callback=self.display.display_scan_progress)
        if hasattr(self.display, 'finalize_progress_display') and self.display._displaying_progress: self.display.finalize_progress_display()
        if not self.current_job_state.processed_files: self.display.display_warning("Nie znaleziono żadnych pasujących plików."); self.current_job_state.status = "Zakończono (brak plików)"; self.current_job_state.end_time = datetime.now(); self.job_state_manager.save_job_state(self.current_job_state); self.display.press_enter_to_continue(); self.current_job_state = None; return
        self.display.display_success(f"Skanowanie zakończone. Znaleziono {self.current_job_state.total_files} plików."); self.current_job_state.status = "Gotowe do przetworzenia"; self.job_state_manager.save_job_state(self.current_job_state)
        first_file_info = self.current_job_state.processed_files[0] if self.current_job_state.processed_files else None; first_output_path = None
        if first_file_info: first_output_path = self.path_resolver.get_output_path_for_transcoding(original_file_path=first_file_info.original_path, profile=selected_profile)
        if first_output_path: self._display_pre_job_summary(self.current_job_state, first_file_info, first_output_path, selected_profile)
        else: self.display.display_warning("Nie można wygenerować ścieżki wyjściowej dla podsumowania.")
        confirm_choice = self.display.get_user_choice(f"Rozpocząć transkodowanie {self.current_job_state.total_files} plików? ({styles.STYLE_PROMPT}tak/nie{styles.ANSI_RESET}): ").lower()
        if confirm_choice != 'tak':
            self.display.display_info("Transkodowanie odroczone."); self.current_job_state.status = "Oczekuje na potwierdzenie"; self.job_state_manager.save_job_state(self.current_job_state)
            self.display.press_enter_to_continue(); self.current_job_state = None; return
        self._process_job_with_multiple_files()

    def _process_job_with_multiple_files(self, is_resuming: bool = False):
        # ... (logika jak w #66)
        if not self.current_job_state or not self.current_job_state.processed_files: self.display.display_error("Brak aktywnego zadania lub plików do przetworzenia."); return
        self.is_processing = True; job = self.current_job_state
        if not is_resuming: job.status = "W toku"; job.start_time = datetime.now()
        else: job.status = "Wznawianie"
        self.job_state_manager.save_job_state(job); selected_profile = self.profiler.get_profile_by_id(str(job.selected_profile_id))
        if not selected_profile:
            job.status = "Błąd krytyczny"; job.error_message = f"Nie znaleziono profilu ID: {job.selected_profile_id}";
            for pf in job.processed_files: pf.status = "Błąd profilu"; pf.error_message = job.error_message or ""; pf.end_time = datetime.now()
            job.end_time = datetime.now(); self.job_state_manager.save_job_state(job); self.display.display_error(job.error_message or "Błąd profilu."); self.is_processing = False; return
        processed_overall = sum(1 for pf in job.processed_files if pf.status == "Ukończono"); failed_overall = sum(1 for pf in job.processed_files if pf.status in ["Błąd", "Błąd (MediaInfo)", "Błąd profilu", "Błąd odczytu"]); skipped_overall = sum(1 for pf in job.processed_files if pf.status.startswith("Pominięto")); error_handling = self.config_manager.get_config_value('processing', 'error_handling', 'skip'); total_files_in_job = len(job.processed_files)
        for idx, file_item in enumerate(job.processed_files):
            current_file_number = idx + 1; self.display.clear_screen()
            job_stats_panel_title = f"{styles.ICON_STATUS} Postęp Zadania: {job.job_id} ({job.status})"
            job_stats_lines = [f"Pliki ukończone: {styles.STYLE_SUCCESS}{processed_overall}{styles.ANSI_RESET} / {total_files_in_job}", f"Pliki z błędem: {styles.STYLE_ERROR}{failed_overall}{styles.ANSI_RESET} / {total_files_in_job}", f"Pliki pominięte: {styles.STYLE_WARNING}{skipped_overall}{styles.ANSI_RESET} / {total_files_in_job}", f"Pozostało do przetworzenia: {max(0, total_files_in_job - (processed_overall + failed_overall + skipped_overall))}"]
            if self.rich_console and Panel and Text and Padding:
                stats_text_obj = Text.from_ansi("\n".join(job_stats_lines)); clean_title = re.sub(r'\x1b\[[0-9;]*m', '', job_stats_panel_title); self.rich_console.print(Panel(Padding(stats_text_obj, (0, 2)), title=clean_title, border_style="magenta", expand=False))
            else: 
                self.display.display_header(job_stats_panel_title)
                for line in job_stats_lines: self.display.display_info(f"  {line}")
                self.display.display_separator()
            panel_title_file = f"{styles.STYLE_PROCESSING_FILE}--- Przetwarzanie pliku {current_file_number}/{total_files_in_job}: {file_item.original_path.name} ---{styles.ANSI_RESET}"; tentative_output_path = self.path_resolver.get_output_path_for_transcoding(file_item.original_path, selected_profile); content_text_file = self._build_file_info_text(title="", file_path=file_item.original_path, media_info=file_item.media_info, output_path=tentative_output_path, profile=selected_profile)
            if self.rich_console and Panel and Text and Padding:
                panel_content_file = Text.from_ansi(content_text_file.strip()); clean_title_file = re.sub(r'\x1b\[[0-9;]*m', '', panel_title_file); self.rich_console.print(Panel(Padding(panel_content_file, (0,1)), title=clean_title_file, border_style="green", expand=False))
            else: 
                self.display.display_message(panel_title_file); plain_content_for_fallback = re.sub(r'\x1b\[[0-9;]*m', '', content_text_file)
                for line in plain_content_for_fallback.strip().split('\n'):
                    if line.strip(): self.display.display_info(f"  {line.strip()}")
            self.display.display_separator(length=60)
            if file_item.status in ["Ukończono", "Pominięto (konflikt)"]: logger.info(f"Pomijanie pliku '{file_item.original_path.name}' (status: {file_item.status})"); time.sleep(0.1); continue
            if file_item.status in ["Błąd", "Błąd odczytu", "Błąd (MediaInfo)", "Przetwarzanie"]: self.display.display_warning(f"Ponawianie pliku ({file_item.status}): {file_item.error_message or ''}"); file_item.status = "Oczekuje"; file_item.error_message = None; file_item.start_time = None; file_item.end_time = None
            if file_item.status != "Oczekuje": self.display.display_info(f"Nieoczekiwany status pliku '{file_item.original_path.name}': {file_item.status}. Pomijanie."); skipped_overall +=1; continue
            if not file_item.media_info or file_item.media_info.duration is None or file_item.media_info.duration <= 0:
                err_msg = "Brak/nieprawidłowe MediaInfo."; self.display.display_error(f"Nie można przetworzyć '{file_item.original_path.name}': {err_msg}"); file_item.status = "Błąd (MediaInfo)"; file_item.error_message = err_msg; file_item.end_time = datetime.now(); failed_overall += 1; self.job_state_manager.save_job_state(job)
                if error_handling == 'stop': job.status = "Zatrzymano (błąd pliku)"; job.error_message = (job.error_message or "") + f"\nZatrzymano przy: {file_item.original_path.name}"; job.end_time = datetime.now(); self.job_state_manager.save_job_state(job); self.is_processing = False; return
                time.sleep(1); continue
            target_output_path = tentative_output_path; conflict_action = self.config_manager.get_config_value('processing', 'output_file_exists', 'rename'); final_output_path = target_output_path
            if target_output_path.exists():
                if conflict_action == 'skip': self.display.display_warning(f"Plik '{target_output_path.name}' już istnieje. Pomijanie."); file_item.status = "Pominięto (konflikt)"; file_item.error_message = "Plik wyjściowy istniał."; file_item.output_path = target_output_path; file_item.end_time = datetime.now(); skipped_overall +=1; self.job_state_manager.save_job_state(job); time.sleep(0.5); continue
                elif conflict_action == 'overwrite': self.display.display_warning(f"Plik '{target_output_path.name}' już istnieje. Zostanie nadpisany.")
                elif conflict_action == 'rename': final_output_path = self.path_resolver.generate_unique_output_path(target_output_path); self.display.display_info(f"Plik '{target_output_path.name}' już istnieje. Zapis jako '{final_output_path.name}'.")
            file_item.output_path = final_output_path; file_item.status = "Przetwarzanie"; file_item.start_time = datetime.now(); self.job_state_manager.save_job_state(job)
            if hasattr(self.display, '_progress_bar_first_draw'): self.display._progress_bar_first_draw = True
            success, error_msg_transcode = self.ffmpeg_manager.transcode_file(input_file_path=file_item.original_path, output_file_path=file_item.output_path, profile=selected_profile, media_info=file_item.media_info, file_index=current_file_number, total_files_in_job=total_files_in_job)
            if hasattr(self.display, 'finalize_progress_display'): self.display.finalize_progress_display()
            file_item.end_time = datetime.now()
            if success:
                file_item.status = "Ukończono"; file_item.error_message = None; processed_overall +=1; self.display.display_success(f"Transkodowanie pliku '{file_item.original_path.name}' zakończone pomyślnie.")
                if self.config_manager.get_config_value('processing', 'delete_original_on_success', False):
                    self.display.display_info(f"Usuwanie oryginalnego pliku: {file_item.original_path.name}");
                    try: file_item.original_path.unlink(); self.display.display_success(f"Usunięto oryginalny plik.")
                    except OSError as e: err_del = f"Błąd usuwania oryginalnego pliku: {e}"; self.display.display_error(err_del); logger.error(err_del, exc_info=True); file_item.error_message = (file_item.error_message or "") + f" | {err_del}"
            else:
                file_item.status = "Błąd"; failed_overall +=1; file_item.error_message = error_msg_transcode or "Nieznany błąd FFmpeg."
                self.display.display_error(f"Błąd podczas transkodowania pliku '{file_item.original_path.name}': {file_item.error_message}")
                if file_item.output_path and file_item.output_path.exists():
                    try: file_item.output_path.unlink(missing_ok=True)
                    except OSError as e_del: logger.warning(f"Nie można usunąć częściowego pliku wyjściowego {file_item.output_path}: {e_del}")
                if error_handling == 'stop': self.display.display_error("Zatrzymano zadanie z powodu błędu pliku."); job.status = "Zatrzymano (błąd pliku)"; job.error_message = (job.error_message or "") + f"\nZatrzymano przy: {file_item.original_path.name}"; job.end_time = datetime.now(); self.job_state_manager.save_job_state(job); self.is_processing = False; return
            self.job_state_manager.save_job_state(job)
            if idx < total_files_in_job -1 : time.sleep(1) 
        job.end_time = datetime.now()
        if failed_overall > 0 and job.status != "Zatrzymano (błąd pliku)": job.status = "Ukończono z błędami"; job.error_message = (job.error_message or "") + f" Niepowodzenia: {failed_overall}/{total_files_in_job}."
        elif processed_overall == (total_files_in_job - skipped_overall - failed_overall) and job.status not in ["Zatrzymano (błąd pliku)", "Anulowano przez użytkownika"]: job.status = "Ukończono";
        if skipped_overall > 0 and job.status.startswith("Ukończono"): job.status += f" (pominięto {skipped_overall})"
        if failed_overall > 0 and error_handling == 'skip' and job.status.startswith("Ukończono"): job.status += f" (błędy: {failed_overall})"
        self.job_state_manager.save_job_state(job); self.display.clear_screen(); self.display.display_message(f"\n--- {styles.ICON_SUCCESS if not failed_overall and job.status == 'Ukończono' else styles.ICON_WARNING} Zakończono zadanie {job.job_id} ---", style=styles.STYLE_HEADER)
        self.display.display_info(f"Status zadania: {job.status}")
        if job.error_message and job.status != "Ukończono" and not job.status.startswith("Ukończono (pominięto"): self.display.display_warning(f"Komunikat: {job.error_message}")
        self.display.display_success(f"Pomyślnie przetworzono (łącznie): {processed_overall} plików."); self.display.display_error(f"Niepowodzenia (łącznie): {failed_overall} plików."); self.display.display_warning(f"Pominięto (łącznie): {skipped_overall} plików.")
        self.is_processing = False; self.current_job_state = None; self.display.press_enter_to_continue()

    def resume_last_job_cli(self): 
        logger.debug("resume_last_job_cli rozpoczęte.")
        if self.is_processing: self.display.display_warning("Inne zadanie jest aktualnie w toku."); self.display.press_enter_to_continue(); return
        last_job = self.job_state_manager.load_last_job_state()
        if not last_job: self.display.display_warning("Brak ostatniego zadania do wznowienia."); self.display.press_enter_to_continue(); return
        eligible_for_resume = False
        if last_job.status not in ["Ukończono", "Ukończono z błędami", "Anulowano przez użytkownika", "Zakończono (brak plików)", "Błąd krytyczny", "Zatrzymano (błąd pliku)"]:
            if last_job.status == "Oczekuje na potwierdzenie": eligible_for_resume = True
            elif hasattr(last_job, 'processed_files') and last_job.processed_files:
                for pf in last_job.processed_files:
                    if pf.status in ["Oczekuje", "Błąd", "Błąd odczytu", "Błąd (MediaInfo)", "Przetwarzanie"]: eligible_for_resume = True; break
        if not eligible_for_resume:
            self.display.display_info(f"Ostatnie zadanie (ID: {last_job.job_id}) ma status '{last_job.status}' lub wszystkie pliki są przetworzone/pominięte. Nie można wznowić.")
            if last_job.status not in ["Ukończono", "Ukończono z błędami", "Anulowano przez użytkownika", "Zakończono (brak plików)", "Zatrzymano (błąd pliku)", "Błąd krytyczny"]: last_job.status = "Ukończono (brak plików do wznowienia)"; last_job.end_time = datetime.now(); self.job_state_manager.save_job_state(last_job)
            self.display.press_enter_to_continue(); return
        self.display.clear_screen(); self.display.display_header(f"{styles.ICON_RESUME} Wznawianie ostatniego zadania"); self.display.display_job_state(last_job)
        files_to_process_count = sum(1 for pf in last_job.processed_files if pf.status in ["Oczekuje", "Błąd", "Błąd odczytu", "Błąd (MediaInfo)", "Przetwarzanie"]) if hasattr(last_job, 'processed_files') else 0
        prompt_msg = f"Czy chcesz wznowić/rozpocząć przetwarzanie ({files_to_process_count} plików) w tym zadaniu? ({styles.STYLE_PROMPT}tak/nie{styles.ANSI_RESET}): "
        if last_job.status == "Oczekuje na potwierdzenie": prompt_msg = f"Zadanie oczekuje na potwierdzenie. Rozpocząć przetwarzanie ({files_to_process_count} plików)? ({styles.STYLE_PROMPT}tak/nie{styles.ANSI_RESET}): "
        confirm_choice = self.display.get_user_choice(prompt_msg).lower()
        if confirm_choice != 'tak': self.display.display_info("Wznawianie/rozpoczęcie zadania anulowane."); self.display.press_enter_to_continue(); return
        self.current_job_state = last_job; self.current_job_state.status = "Wznawianie"; self.current_job_state.error_message = None; self.job_state_manager.save_job_state(self.current_job_state)
        self._process_job_with_multiple_files(is_resuming=True)

    def display_last_job_state_cli(self): 
        logger.debug("display_last_job_state_cli rozpoczęte.")
        self.display.clear_screen(); self.display.display_header(f"{styles.ICON_STATUS} Stan ostatniego zadania")
        last_job = self.job_state_manager.load_last_job_state()
        if last_job: self.display.display_job_state(last_job)
        else: self.display.display_info("Brak zapisanego stanu ostatniego zadania.")
        self.display.press_enter_to_continue()

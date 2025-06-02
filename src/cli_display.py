# src/cli_display.py
import logging
import shutil
from typing import Optional, Any, Dict, List, Union, Tuple, Callable
from datetime import datetime, timedelta
import sys
from pathlib import Path
import json
import re
import time

try:
    import readchar
    from readchar import key as readchar_key
    READCHAR_AVAILABLE = True
except ImportError:
    READCHAR_AVAILABLE = False
    readchar = None # type: ignore
    readchar_key = None # type: ignore
    class PlaceholderReadcharKey: # type: ignore
        UP = "UP_ARROW_KEY_UNAVAILABLE"; DOWN = "DOWN_ARROW_KEY_UNAVAILABLE"
        ENTER = "ENTER_KEY_UNAVAILABLE"; ESC = "ESC_KEY_UNAVAILABLE"
        CR = "CR_KEY_UNAVAILABLE"
    readchar_key = PlaceholderReadcharKey() # type: ignore

try:
    from .models import JobState, ProcessedFile, EncodingProfile, MediaInfo # type: ignore
except ImportError:
    JobState, ProcessedFile, EncodingProfile, MediaInfo = None, None, None, None # type: ignore
    pass

try:
    from . import cli_styles as styles # type: ignore
except ImportError:
    class PlaceholderStyles: # type: ignore
        ANSI_RESET = ''; STYLE_HEADER = ''; STYLE_SEPARATOR = ''; STYLE_INFO = ''; STYLE_SUCCESS = ''
        STYLE_WARNING = ''; STYLE_ERROR = ''; STYLE_PROMPT = ''; STYLE_PROCESSING_FILE = ''
        STYLE_PROGRESS_BAR_FILL = ''; STYLE_PROGRESS_BAR_EMPTY = ''; STYLE_PROGRESS_TEXT = ''
        STYLE_SYSTEM_MONITOR_HEADER = ''; STYLE_SYSTEM_MONITOR_LABEL = ''; STYLE_SYSTEM_MONITOR_VALUE = ''
        STYLE_CONFIG_VALUE = ''; STYLE_MENU_HIGHLIGHT = ''; STYLE_MENU_DEFAULT = ''; STYLE_MENU_DESCRIPTION = ''
        ICON_ARROW_RIGHT = "> "; ICON_SETTINGS = "S"; ICON_PLAY = "P"; ICON_FOLDER_SCAN = "FS"
        ICON_RESUME = "R"; ICON_STATUS = "ST"; ICON_PROFILE = "Prof"; ICON_BROKEN_FILE = "BF"
        ICON_REPAIR = "Fix"; ICON_LIST = "L"; ICON_CONFIG = "C"; ICON_LOG = "Log"
        ICON_MONITOR = "M"; ICON_EXIT = "E"; ICON_SUCCESS = "OK"; ICON_ERROR = "ERR"
        ICON_PERCENT = "%"; ICON_TIME_ETA = "ETA"; ICON_FPS = "FPS"
        ICON_SPEED = "SPD"; ICON_BITRATE = "BR"; ICON_OUTPUT_SIZE = "SIZE"
        ICON_CPU = "CPU"; ICON_RAM = "RAM"; ICON_DISK = "DISK"; ICON_DELETE = "DEL"
        BOX_HL = "-"; BOX_VL = "|"; BOX_TL = "+"; BOX_TR = "+"; BOX_BL = "+"; BOX_BR = "+"
        STYLE_FRAME = ""
    styles = PlaceholderStyles() # type: ignore

from .transcoding_display_formatter import TranscodingDisplayFormatter
try:
    from ..system_monitor.resource_monitor import ResourceMonitor # type: ignore
except ImportError:
    ResourceMonitor = None # type: ignore

logger = logging.getLogger(__name__)
MenuOption = Tuple[str, str, Optional[str]]

def get_visual_length_approx(text_with_styles: str) -> int:
    plain_text = re.sub(r'\x1b\[[0-9;]*[mK]', '', text_with_styles)
    for icon_name in dir(styles):
        if icon_name.startswith("ICON_") and isinstance(getattr(styles, icon_name), str):
            icon_val = getattr(styles, icon_name)
            if len(icon_val) > 0: plain_text = plain_text.replace(icon_val, "X")
    return len(plain_text)

class CLIDisplay:
    def __init__(self, resource_monitor: Optional[ResourceMonitor] = None):
        logger.debug("CLIDisplay: Inicjalizacja rozpoczęta.")
        self._displaying_progress = False; self._num_progress_lines_written = 0
        self.progress_bar_char_width = 40
        self.formatter = TranscodingDisplayFormatter()
        self.resource_monitor = resource_monitor
        self._last_sys_info_update_time: float = 0.0; self._sys_info_update_interval: float = 1.0
        self._menu_sys_info_update_interval: float = 2.0
        self._last_menu_sys_info_str: str = ""; self._last_menu_sys_info_fetch_time: float = 0.0
        self._current_sys_info_line: str = ""; self._progress_bar_first_draw: bool = True
        if not READCHAR_AVAILABLE and sys.stdin.isatty(): logger.warning("Biblioteka 'readchar' niedostępna. Nawigacja strzałkami w menu nie będzie działać.")
        if self.resource_monitor is None: logger.warning("ResourceMonitor nie przekazany. Info o systemie nie będzie wyświetlane.")
        logger.debug("CLIDisplay: Inicjalizacja zakończona.")

    def set_progress_bar_width(self, width: int): self.progress_bar_char_width = max(10, width)
    def get_terminal_width(self) -> int:
        try: columns, _ = shutil.get_terminal_size(fallback=(80, 24)); return columns
        except Exception: return 80

    def clear_screen(self):
        if self._displaying_progress and self._num_progress_lines_written > 0: self.finalize_progress_display()
        sys.stdout.write('\033[H\033[J'); sys.stdout.flush(); logger.debug("CLIDisplay: Ekran wyczyszczony.")

    def _clear_last_n_lines(self, num_lines: int):
        if num_lines <= 0 or not sys.stdout.isatty(): return
        sys.stdout.write(f'\r\033[{num_lines-1}A');
        for _ in range(num_lines): sys.stdout.write('\033[K\n')
        sys.stdout.write(f'\r\033[{num_lines}A'); sys.stdout.flush()

    def display_message(self, message: str, style: str = styles.STYLE_INFO, new_line: bool = True):
        if self._displaying_progress and self._num_progress_lines_written > 0: self.finalize_progress_display()
        sys.stdout.write(f"{style}{message}{styles.ANSI_RESET}{'\n' if new_line else ''}"); sys.stdout.flush()

    def display_header(self, text: str): self.display_message(text, styles.STYLE_HEADER); self.display_separator(); logger.debug(f"Wyświetlono nagłówek: {text}")
    def display_separator(self, length: Optional[int] = None):
        term_w = self.get_terminal_width(); sep_l = min(length if length is not None else max(20, term_w), term_w)
        self.display_message(styles.BOX_HL * sep_l, styles.STYLE_SEPARATOR)

    def display_info(self, message: str): self.display_message(message, styles.STYLE_INFO)
    def display_success(self, message: str): self.display_message(message, styles.STYLE_SUCCESS)
    def display_warning(self, message: str): self.display_message(message, styles.STYLE_WARNING)
    def display_error(self, message: str): self.display_message(message, styles.STYLE_ERROR)

    def display_prompt(self, message: str) -> str:
        if self._displaying_progress and self._num_progress_lines_written > 0: self.finalize_progress_display()
        self.display_message(f"{message}", style=styles.STYLE_PROMPT, new_line=False); sys.stdout.flush()
        try: return sys.stdin.readline().strip()
        except KeyboardInterrupt: print(""); logger.info("Przerwanie wprowadzania danych (Ctrl+C)."); raise

    def get_user_choice(self, message: str = "Wybierz opcję: ") -> str: return self.display_prompt(message + (" " if not message.endswith(" ") else ""))
    def press_enter_to_continue(self, msg: str = "Naciśnij ENTER, aby kontynuować..."): self.display_prompt(f"\n{msg} "); logger.debug("press_enter_to_continue zakończone.")

    def _render_menu_options_within_frame(self, options: List[MenuOption], current_selection_index: int, frame_inner_width: int):
        # ... (implementacja jak w prompt #32) ...
        text_padding_left = 1; key_icon_prefix_max_width = 8 
        available_text_width = frame_inner_width - key_icon_prefix_max_width - text_padding_left - 1
        for index, (key, text, icon) in enumerate(options):
            prefix_icon_str = f"{icon} " if icon else ""
            key_display_str = f"{key}." if key.isalnum() and len(key) == 1 and key.isdigit() else f"{key}"
            display_text_final = text; plain_text_for_len_calc = re.sub(r'\x1b\[[0-9;]*m', '', text)
            if len(plain_text_for_len_calc) > available_text_width:
                if available_text_width > 3:
                    main_part_plain, desc_part_plain = plain_text_for_len_calc, ""
                    separator_candidate = f" {styles.STYLE_MENU_DESCRIPTION}- "
                    original_parts = text.split(separator_candidate, 1); main_part_styled = original_parts[0]
                    if len(plain_text_for_len_calc.split(" - ", 1)) > 1 :
                        plain_parts = plain_text_for_len_calc.split(" - ", 1); main_part_plain = plain_parts[0]
                        if len(plain_parts) > 1: desc_part_plain = plain_parts[1]
                    else: main_part_plain = plain_text_for_len_calc; desc_part_plain = ""
                    if get_visual_length_approx(main_part_styled) > available_text_width - 3:
                        main_part_styled_short = main_part_plain[:available_text_width - 3] + "..."
                        display_text_final = main_part_styled_short
                    else:
                        display_text_final = main_part_styled
                        remaining_width_for_desc = available_text_width - get_visual_length_approx(main_part_styled) - get_visual_length_approx(f" {styles.STYLE_MENU_DESCRIPTION}- {styles.ANSI_RESET}") -3
                        if remaining_width_for_desc > 3 and desc_part_plain:
                            desc_part_short = desc_part_plain[:remaining_width_for_desc] + "..."
                            display_text_final += f" {styles.STYLE_MENU_DESCRIPTION}- {desc_part_short}{styles.ANSI_RESET}"
                else: display_text_final = plain_text_for_len_calc[:available_text_width]
            menu_line_core_content = f"{' '*text_padding_left}{prefix_icon_str}{key_display_str:<3} {display_text_final}"
            current_visual_len = get_visual_length_approx(menu_line_core_content)
            padding_needed = frame_inner_width - current_visual_len
            final_line_str: str
            if index == current_selection_index:
                core_no_reset = menu_line_core_content.removesuffix(styles.ANSI_RESET) if menu_line_core_content.endswith(styles.ANSI_RESET) else menu_line_core_content
                final_line_str = f"{styles.STYLE_MENU_HIGHLIGHT}{core_no_reset}{' '*max(0,padding_needed)}{styles.ANSI_RESET}"
            else:
                default_padding = " " * max(0,padding_needed)
                core_content_no_style = menu_line_core_content
                start_style = styles.STYLE_MENU_DEFAULT; end_style = styles.ANSI_RESET
                if core_content_no_style.startswith(start_style): core_content_no_style = core_content_no_style[len(start_style):]
                if core_content_no_style.endswith(end_style): core_content_no_style = core_content_no_style[:-len(end_style)]
                final_line_str = f"{start_style}{core_content_no_style}{default_padding}{end_style}"
            sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_VL}{styles.ANSI_RESET}" \
                             f"{final_line_str.ljust(frame_inner_width)[:frame_inner_width]}" \
                             f"{styles.STYLE_FRAME}{styles.BOX_VL}{styles.ANSI_RESET}\n")
        sys.stdout.flush()

    def present_interactive_menu(
        self, header_text: str, menu_options: List[MenuOption],
        prompt_message: str = "Wybierz opcję:", 
        allow_numeric_select: bool = True,
        initial_selection_index: Optional[int] = None
    ) -> Tuple[str, int]:
        if not READCHAR_AVAILABLE or not sys.stdin.isatty():
            logger.warning("Interaktywne menu niedostępne, używam trybu standardowego.")
            self.clear_screen(); self.display_header(header_text)
            idx_map = {opt[0]: i for i, opt in enumerate(menu_options)}
            for i, (key, text, icon) in enumerate(menu_options): self.display_info(f"  {icon or ''} {key}. {text}")
            self.display_separator(); chosen_key = self.get_user_choice(prompt_message.split(':')[0] + ": ")
            return chosen_key, idx_map.get(chosen_key, 0)

        current_selection_index = 0
        if initial_selection_index is not None and 0 <= initial_selection_index < len(menu_options):
            current_selection_index = initial_selection_index
        
        terminal_width = self.get_terminal_width()
        frame_inner_width = terminal_width - 2; text_padding_left = 1
        if frame_inner_width < 10: frame_inner_width = 10

        sys.stdout.write("\033[?25l"); sys.stdout.flush()
        exit_keys = [opt[0] for opt in menu_options if opt[0] in ['0', 'q', 'Q']]

        try:
            while True:
                self.clear_screen(); title_padding = 1
                plain_header = re.sub(r'\x1b\[[0-9;]*m', '', header_text)
                max_title_len = frame_inner_width - 2 - (2*title_padding)
                title_disp = plain_header[:max_title_len-3]+"..." if len(plain_header)>max_title_len and max_title_len>3 else plain_header[:max_title_len]
                title_styled = f"{styles.STYLE_HEADER}{' '*title_padding}{title_disp}{' '*title_padding}{styles.ANSI_RESET}"
                title_vis_len = get_visual_length_approx(title_styled)
                title_bar_fill_area = frame_inner_width - 2 
                if title_bar_fill_area < 0: title_bar_fill_area = 0
                hl_total = max(0, title_bar_fill_area - title_vis_len)
                title_bar_content = f"{styles.BOX_HL*(hl_total//2)}{title_styled}{styles.BOX_HL*(hl_total - hl_total//2)}"
                current_title_bar_len = get_visual_length_approx(title_bar_content)
                if current_title_bar_len < title_bar_fill_area: title_bar_content += styles.BOX_HL * (title_bar_fill_area - current_title_bar_len)
                elif current_title_bar_len > title_bar_fill_area:
                     plain_title_bar_content = re.sub(r'\x1b\[[0-9;]*m', '', title_bar_content)
                     title_bar_content = (styles.STYLE_FRAME or "") + plain_title_bar_content[:title_bar_fill_area] + styles.ANSI_RESET
                
                sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_TL}{title_bar_content}{styles.BOX_TR}{styles.ANSI_RESET}\n")
                self._render_menu_options_within_frame(menu_options, current_selection_index, frame_inner_width)

                status_line_content = ""; current_time_for_status = time.time()
                if self.resource_monitor and self.resource_monitor.is_available():
                    if current_time_for_status - self._last_menu_sys_info_fetch_time > self._menu_sys_info_update_interval or not self._last_menu_sys_info_str:
                        cpu = self.resource_monitor.get_cpu_usage(); ram = self.resource_monitor.get_ram_usage()
                        cpu_s = f"{styles.ICON_CPU}{cpu:.0f}%" if cpu is not None else f"{styles.ICON_CPU}N/A"
                        ram_s = f"{styles.ICON_RAM}{ram['percent']:.0f}%" if ram else f"{styles.ICON_RAM}N/A"
                        self._last_menu_sys_info_str = f"{cpu_s} | {ram_s} | 🕒 {datetime.now().strftime('%H:%M:%S')}"
                        self._last_menu_sys_info_fetch_time = current_time_for_status
                    status_line_content = self._last_menu_sys_info_str
                else: status_line_content = f"{styles.STYLE_WARNING}Monitor zasobów N/A{styles.ANSI_RESET}"
                vis_len_status = get_visual_length_approx(status_line_content)
                pad_stat_total = frame_inner_width - vis_len_status
                stat_line_formatted = f"{' '*(pad_stat_total//2)}{status_line_content}{' '*(pad_stat_total - pad_stat_total//2)}"
                stat_line_formatted = stat_line_formatted[:frame_inner_width] 
                sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_VL}{styles.STYLE_INFO}{stat_line_formatted}{styles.ANSI_RESET}{styles.STYLE_FRAME}{styles.BOX_VL}{styles.ANSI_RESET}\n")
                
                sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_VL}{styles.BOX_HL * frame_inner_width}{styles.BOX_VL}{styles.ANSI_RESET}\n")
                plain_prompt = re.sub(r'\x1b\[[0-9;]*m', '', prompt_message)
                max_prompt_len = frame_inner_width - (2*text_padding_left);
                prompt_disp = plain_prompt[:max_prompt_len-3]+"..." if len(plain_prompt)>max_prompt_len and max_prompt_len>3 else plain_prompt[:max_prompt_len]
                prompt_text_part = f"{' '*text_padding_left}{prompt_disp}"
                prompt_line = prompt_text_part + " " * max(0, frame_inner_width - get_visual_length_approx(prompt_text_part))
                sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_VL}{styles.STYLE_PROMPT}{prompt_line}{styles.ANSI_RESET}{styles.STYLE_FRAME}{styles.BOX_VL}{styles.ANSI_RESET}\n")
                
                sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_BL}{styles.BOX_HL*frame_inner_width}{styles.BOX_BR}{styles.ANSI_RESET}\n"); sys.stdout.flush()

                char = readchar.readkey()
                if char == readchar_key.UP: current_selection_index = (current_selection_index - 1 + len(menu_options)) % len(menu_options)
                elif char == readchar_key.DOWN: current_selection_index = (current_selection_index + 1) % len(menu_options)
                elif char in [readchar_key.ENTER, readchar_key.CR]:
                    sys.stdout.write("\033[?25h");sys.stdout.flush();self.clear_screen()
                    return menu_options[current_selection_index][0], current_selection_index
                elif char == readchar_key.ESC:
                    exit_key_choice = next((opt[0] for opt in menu_options if opt[0] in exit_keys), None)
                    if exit_key_choice:
                        idx_of_exit = next((i for i, opt in enumerate(menu_options) if opt[0] == exit_key_choice), current_selection_index)
                        sys.stdout.write("\033[?25h");sys.stdout.flush();self.clear_screen()
                        return exit_key_choice, idx_of_exit
                if allow_numeric_select or (len(char)==1 and not char.isnumeric()): # Zmieniono warunek, aby akceptować wszystkie pojedyncze znaki
                    for idx, (opt_key, _, _) in enumerate(menu_options):
                        if char == opt_key:
                            sys.stdout.write("\033[?25h");sys.stdout.flush();self.clear_screen()
                            return opt_key, idx
        finally:
            sys.stdout.write("\033[?25h"); sys.stdout.flush()

    def display_main_menu(self, initial_selection_index: Optional[int] = None) -> Tuple[str, int]: # <-- POPRAWIONA SYGNATURA
        menu_items: List[MenuOption] = [
            ("1", "Nowe zadanie transkodowania", styles.ICON_PLAY),
            ("2", "Wznów ostatnie zadanie", styles.ICON_RESUME),
            ("3", "Stan ostatniego zadania", styles.ICON_STATUS),
            ("4", "Zarządzaj profilami", styles.ICON_PROFILE),
            ("5", "Skanuj uszkodzone pliki", styles.ICON_FOLDER_SCAN),
            ("6", "Napraw z listy uszkodzonych", styles.ICON_REPAIR),
            ("7", "Zarządzaj listą uszkodzonych", styles.ICON_BROKEN_FILE),
            ("8", "Wyświetl konfigurację", styles.ICON_CONFIG),
            ("9", "Pokaż ścieżkę logu", styles.ICON_LOG),
            ("10", "Ustawienia Aplikacji", styles.ICON_SETTINGS),
            ("11", "Monitor Zasobów", styles.ICON_MONITOR),
            ("0", "Wyjdź z aplikacji", styles.ICON_EXIT)
        ]
        # Przekaż initial_selection_index, jeśli jest None, present_interactive_menu użyje 0
        return self.present_interactive_menu(
            header_text=f"{styles.ICON_SETTINGS} Główne Menu {styles.ICON_SETTINGS}",
            menu_options=menu_items,
            prompt_message="Nawigacja: ↑↓, Enter; Klawisz; ESC",
            allow_numeric_select=True,
            initial_selection_index=initial_selection_index # <-- PRZEKAZANIE PARAMETRU
        )

    def display_job_state(self, job_state: Optional[JobState]):
        if not job_state: self.display_warning("Brak danych o zadaniu."); self.press_enter_to_continue(); return
        title = f"{styles.ICON_STATUS} Szczegóły Zadania: {job_state.job_id} {styles.ICON_STATUS}"
        content_lines = [
            f"{styles.ICON_FOLDER_SCAN} Katalog: {job_state.source_directory.resolve() if hasattr(job_state, 'source_directory') and job_state.source_directory else 'N/A'}",
            f"{styles.ICON_PROFILE} Profil ID: {job_state.selected_profile_id if job_state.selected_profile_id else 'Brak'}",
            f"{styles.ICON_LIST} Plików: {job_state.total_files if hasattr(job_state, 'total_files') else 'N/A'}",
            f"🕒 Start: {job_state.start_time.strftime('%y-%m-%d %H:%M') if job_state.start_time else 'N/A'}",
            f"🕒 Koniec: {job_state.end_time.strftime('%y-%m-%d %H:%M') if job_state.end_time else 'N/A'}"
        ]
        status_icon = styles.ICON_INFO; current_status = job_state.status if job_state.status else "Nieznany"
        if "Ukończono" in current_status: status_icon = styles.ICON_SUCCESS
        elif "Błąd" in current_status or "Zatrzymano" in current_status: status_icon = styles.ICON_ERROR
        elif "W toku" in current_status or "Skanowanie" in current_status : status_icon = styles.ICON_PLAY
        content_lines.insert(1, f"{status_icon} Status: {current_status}")
        if job_state.error_message: content_lines.append(f"{styles.ICON_ERROR}{styles.STYLE_ERROR} Błąd zad.: {job_state.error_message}{styles.ANSI_RESET}")
        self.clear_screen(); self._display_framed_content_block(title, content_lines)
        if hasattr(job_state, 'processed_files') and job_state.processed_files:
            self.display_message(f"\n{styles.STYLE_HEADER}Przetworzone pliki ({len(job_state.processed_files)}):{styles.ANSI_RESET}")
            for i, pf in enumerate(job_state.processed_files):
                pi = styles.ICON_INFO
                if pf.status == "Ukończono": pi = styles.ICON_SUCCESS
                elif "Błąd" in pf.status: pi = styles.ICON_ERROR
                elif pf.status.startswith("Pominięto"): pi = styles.ICON_WARNING
                dur_orig = self.formatter.format_progress_time(pf.media_info.duration) if pf.media_info and pf.media_info.duration is not None else "N/A"
                out_name = pf.output_path.name if pf.output_path else "N/A"
                self.display_info(f" {i+1}. {pi} {pf.original_path.name} -> {out_name} ({pf.status}, {dur_orig})")
                if pf.error_message: self.display_error(f"    Błąd pliku: {pf.error_message}")
        elif not hasattr(job_state, 'processed_files') or not job_state.processed_files :
             self.display_warning("Brak szczegółów plików w tym zadaniu.")
        self.press_enter_to_continue(); logger.debug(f"Wyświetlono stan zadania {job_state.job_id}.")

    def display_scan_progress(self, current_file_num: int, total_files: int, file_name: str):
        if self._displaying_progress: self.finalize_progress_display()
        message = f"Skanowanie: {current_file_num}/{total_files} -> {file_name}"
        sys.stdout.write(f"\r{styles.STYLE_INFO}{message}{styles.ANSI_RESET}\033[K"); sys.stdout.flush()

    def display_progress_bar(self,
                             percentage: float, elapsed_time: float, file_name: str,
                             file_index: Optional[int] = None, total_files_in_job: Optional[int] = None,
                             fps: Optional[float] = None, speed: Optional[str] = None,
                             bitrate: Optional[str] = None, eta_seconds_file: Optional[float] = None,
                             output_size_str: Optional[str] = None, output_file_path_str: Optional[str] = None):
        terminal_width = self.get_terminal_width()
        file_prefix_str = f"{styles.ICON_LIST}{file_index or '?'}/{total_files_in_job or '?'} "
        percent_str = f"{styles.ICON_PERCENT}[{self.formatter.format_percentage(percentage)}]"
        time_eta_str = f"{styles.ICON_TIME_ETA}[{self.formatter.format_progress_time(elapsed_time)}/{self.formatter.format_eta(eta_seconds_file)}]"
        opt_parts = []
        if speed and "---" not in (s:=self.formatter.format_speed(speed)): opt_parts.append(f"{styles.ICON_SPEED}[{s}]")
        if fps and "----" not in (s:=self.formatter.format_fps(fps)): opt_parts.append(f"{styles.ICON_FPS}[{s}]")
        if bitrate and "----" not in (s:=self.formatter.format_bitrate(bitrate)): opt_parts.append(f"{styles.ICON_BITRATE}[{s}]")
        if output_size_str and "----" not in (s:=self.formatter.format_filesize(output_size_str)): opt_parts.append(f"{styles.ICON_OUTPUT_SIZE}[{s}]")
        max_fn_len_progress = 25; display_file_name = file_name
        if len(file_name) > max_fn_len_progress: display_file_name = file_name[:max_fn_len_progress-3] + "..."
        line1_content = f"{display_file_name} {file_prefix_str}{percent_str} {time_eta_str} {' '.join(opt_parts)}"
        visual_len_l1 = get_visual_length_approx(line1_content)
        if visual_len_l1 > terminal_width and opt_parts: line1_content = f"{display_file_name} {file_prefix_str}{percent_str} {time_eta_str}"
        if get_visual_length_approx(line1_content) > terminal_width: line1_content = f"{percent_str} {time_eta_str}"
        line1_display_padded = (line1_content + " " * max(0, terminal_width - get_visual_length_approx(line1_content)))[:terminal_width]
        fill_char = '█'; empty_char = '░'; bar_width_eff = min(self.progress_bar_char_width, terminal_width)
        filled_len = int(bar_width_eff * (percentage / 100.0)); empty_len = bar_width_eff - filled_len
        line2_styled_bar = (f"{styles.STYLE_PROGRESS_BAR_FILL}{fill_char * filled_len}"
                            f"{styles.STYLE_PROGRESS_BAR_EMPTY}{empty_char * empty_len}{styles.ANSI_RESET}")
        line2_display_padded = (line2_styled_bar + " " * max(0, terminal_width - bar_width_eff))[:terminal_width]
        curr_time = time.time()
        if self.resource_monitor and self.resource_monitor.is_available() and \
           (curr_time - self._last_sys_info_update_time > self._sys_info_update_interval or self._progress_bar_first_draw):
            self._last_sys_info_update_time = curr_time
            cpu_u, ram_u, disk_u = self.resource_monitor.get_cpu_usage(), self.resource_monitor.get_ram_usage(), None
            if output_file_path_str:
                try:
                    out_parent = Path(output_file_path_str).parent
                    if out_parent.exists():
                        disk_u = self.resource_monitor.get_specific_disk_usage(out_parent)
                except Exception as e_disk_progress: 
                    logger.warning(f"Błąd informacji o dysku w pasku postępu dla '{output_file_path_str}': {e_disk_progress}", exc_info=False)
            cpu_s = f"{styles.ICON_CPU}{cpu_u:.1f}%" if cpu_u is not None else f"{styles.ICON_CPU}N/A"
            ram_s = f"{styles.ICON_RAM}{ram_u['percent']:.1f}%" if ram_u else f"{styles.ICON_RAM}N/A"
            disk_s = f"{styles.ICON_DISK}{disk_u['free_gb']:.1f}GB" if disk_u else f"{styles.ICON_DISK}N/A"
            self._current_sys_info_line = f"{styles.STYLE_INFO}{cpu_s} | {ram_s} | {disk_s}{styles.ANSI_RESET}"
        elif not self.resource_monitor or not self.resource_monitor.is_available():
            self._current_sys_info_line = f"{styles.STYLE_WARNING}Monitor zasobów niedostępny{styles.ANSI_RESET}"
        line3_display_padded = (self._current_sys_info_line + " " * max(0, terminal_width - get_visual_length_approx(self._current_sys_info_line)))[:terminal_width]
        num_lines = 3
        lines_to_draw_content = [line1_display_padded, line2_display_padded, line3_display_padded]
        if self._progress_bar_first_draw:
            sys.stdout.write('\n' * num_lines)
            sys.stdout.write(f'\033[{num_lines}A')
            sys.stdout.write('\033[s')
            self._progress_bar_first_draw = False
        else:
            sys.stdout.write('\033[u')
        for i in range(num_lines):
            sys.stdout.write('\033[2K')
            sys.stdout.write(lines_to_draw_content[i][:terminal_width])
            if i < num_lines - 1: sys.stdout.write('\n')
        sys.stdout.flush(); self._displaying_progress = True; self._num_progress_lines_written = num_lines

    def finalize_progress_display(self):
        if self._displaying_progress:
            sys.stdout.write('\033[u');
            for _ in range(self._num_progress_lines_written): sys.stdout.write('\033[2K\n')
            if self._num_progress_lines_written > 0: sys.stdout.write(f'\r\033[{self._num_progress_lines_written}A')
            sys.stdout.flush()
        self._displaying_progress = False; self._num_progress_lines_written = 0
        self._progress_bar_first_draw = True; self._current_sys_info_line = ""
        logger.debug("finalize_progress_display: Zakończono i zresetowano pasek postępu.")

    def display_damaged_files_list(self, damaged_files: List[Dict[str, Any]]):
        self.clear_screen(); title = f"{styles.ICON_BROKEN_FILE} Lista Uszkodzonych Plików {styles.ICON_BROKEN_FILE}"; content_lines = []
        if not damaged_files: content_lines.append("Lista uszkodzonych plików jest pusta.")
        else:
            content_lines.append(f"{styles.STYLE_WARNING}Znaleziono {len(damaged_files)} plików:{styles.ANSI_RESET}")
            content_lines.append(styles.BOX_HL * 20)
            for i, entry in enumerate(damaged_files):
                fp_val = entry.get('file_path','N/A'); fp = Path(fp_val) if isinstance(fp_val, (str, Path)) else Path(str(fp_val))
                ts_val = entry.get('timestamp'); ts = ts_val.strftime('%y-%m-%d %H:%M') if isinstance(ts_val,datetime) else str(ts_val)
                ed = entry.get('error_details','Brak'); st=entry.get('status','N/A')
                mi_dur_val = None; mi = entry.get('media_info')
                if isinstance(mi, MediaInfo): mi_dur_val = mi.duration
                elif isinstance(mi, dict): mi_dur_val = mi.get('duration')
                dur = self.formatter.format_progress_time(mi_dur_val) if mi_dur_val is not None else "N/A"
                content_lines.append(f"{i+1}. {styles.ICON_FOLDER_SCAN} {fp.name} ({fp.parent.name})")
                content_lines.append(f"   {styles.ICON_INFO} Status: {st} | Data: {ts} | Długość: {dur}")
                content_lines.append(f"   {styles.ICON_ERROR} Błąd: {ed[:100]}{'...' if len(ed)>100 else ''}")
                if i < len(damaged_files) -1: content_lines.append(f"   {styles.BOX_HL * 10}")
        self._display_framed_content_block(title, content_lines); self.press_enter_to_continue()

    def display_config_dict(self, config_dict: Dict[str, Any]):
        title = f"{styles.ICON_CONFIG} Konfiguracja Aplikacji {styles.ICON_CONFIG}"; content_lines: List[str] = []
        for section, settings in config_dict.items():
            content_lines.append(f"{styles.STYLE_HEADER}[{section}]{styles.ANSI_RESET}")
            if isinstance(settings, dict):
                for key, value in settings.items():
                    dv = str(value.resolve()) if isinstance(value,Path) else ", ".join(map(str,value)) if isinstance(value,list) else str(value) if value is not None else f"{styles.STYLE_WARNING}None{styles.ANSI_RESET}"
                    content_lines.append(f"  {key:<30} = {styles.STYLE_CONFIG_VALUE}{dv}{styles.ANSI_RESET}")
            else: content_lines.append(f"  {section} = {styles.STYLE_CONFIG_VALUE}{settings}{styles.ANSI_RESET}")
            content_lines.append("")
        self.clear_screen(); self._display_framed_content_block(title, content_lines); self.press_enter_to_continue()
        logger.debug("Wyświetlono konfigurację w ramce.")

    def _display_framed_content_block(self, title: str, content_lines: List[str], footer_text: Optional[str] = None):
        terminal_width = self.get_terminal_width(); frame_inner_width = terminal_width - 2
        if frame_inner_width < 10: frame_inner_width = 10; text_pad_left = 0
        else: text_pad_left = 1
        plain_title = re.sub(r'\x1b\[[0-9;]*m', '', title); title_disp_raw = f" {plain_title} "
        title_text_max_visual_len = frame_inner_width - 2
        title_final_display_text : str
        if get_visual_length_approx(title_disp_raw) > title_text_max_visual_len : title_final_display_text = title_disp_raw[:max(0, title_text_max_visual_len -3 )] + "..." if title_text_max_visual_len >3 else title_disp_raw[:title_text_max_visual_len]
        else: title_final_display_text = title_disp_raw
        title_styled = f"{styles.STYLE_HEADER}{title_final_display_text}{styles.ANSI_RESET}"
        title_bar_visual_len = get_visual_length_approx(title_styled)
        hl_fill_total = frame_inner_width -2 - title_bar_visual_len;
        if hl_fill_total < 0: hl_fill_total = 0
        hl_l = hl_fill_total // 2; hl_r = hl_fill_total - hl_l
        title_bar_content = f"{styles.BOX_HL*hl_l}{title_styled}{styles.BOX_HL*hl_r}"
        current_title_bar_len = get_visual_length_approx(title_bar_content)
        title_bar_padded = title_bar_content + styles.BOX_HL * max(0, (frame_inner_width - 2) - current_title_bar_len)
        if get_visual_length_approx(title_bar_padded) > frame_inner_width -2:
             plain_title_bar_padded = re.sub(r'\x1b\[[0-9;]*m', '', title_bar_padded)
             title_bar_padded = (styles.STYLE_FRAME or "") + plain_title_bar_padded[:frame_inner_width-2] + styles.ANSI_RESET

        sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_TL}{title_bar_padded}{styles.BOX_TR}{styles.ANSI_RESET}\n")

        for line_raw in content_lines:
            line_to_print_buffer = f"{' '*text_pad_left}{line_raw}"
            visual_len = get_visual_length_approx(line_to_print_buffer)
            if visual_len > frame_inner_width:
                 plain_line = re.sub(r'\x1b\[[0-9;]*m', '', line_to_print_buffer)
                 line_to_print_buffer = plain_line[:frame_inner_width - (text_pad_left + 3)] + "..."
                 line_to_print_buffer = f"{' '*text_pad_left}{line_to_print_buffer}"
            padding_right = " " * max(0, frame_inner_width - get_visual_length_approx(line_to_print_buffer))
            final_line_display = f"{line_to_print_buffer}{padding_right}"
            sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_VL}{styles.ANSI_RESET}" \
                             f"{final_line_display[:frame_inner_width]}" \
                             f"{styles.STYLE_FRAME}{styles.BOX_VL}{styles.ANSI_RESET}\n")
        if footer_text:
            sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_VL}{styles.BOX_HL*frame_inner_width}{styles.BOX_VL}{styles.ANSI_RESET}\n")
            plain_footer = re.sub(r'\x1b\[[0-9;]*m', '', footer_text); max_f_len=frame_inner_width-(2*text_pad_left)
            if max_f_len < 0 : max_f_len = 0
            f_disp = plain_footer[:max_f_len-3]+"..." if len(plain_footer)>max_f_len and max_f_len > 3 else plain_footer[:max_f_len]
            f_line_content = (f"{' '*text_pad_left}{f_disp}").ljust(frame_inner_width - text_pad_left) # Było justowanie do frame_inner_width, poprawiono
            sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_VL}{styles.STYLE_PROMPT}{f_line_content[:frame_inner_width]}{styles.ANSI_RESET}{styles.STYLE_FRAME}{styles.BOX_VL}{styles.ANSI_RESET}\n")

        sys.stdout.write(f"{styles.STYLE_FRAME}{styles.BOX_BL}{styles.BOX_HL*frame_inner_width}{styles.BOX_BR}{styles.ANSI_RESET}\n"); sys.stdout.flush()

    def display_settings_main_menu(self, current_config: Dict[str, Any]): # Ta metoda jest przestarzała
        self.clear_screen(); title = f"{styles.ICON_SETTINGS} Menu Ustawień {styles.ICON_SETTINGS}"
        content = ["Ta metoda jest przestarzała.", "Logika menu ustawień znajduje się w SettingsCLIHandler.", "", "Proszę użyć opcji w SettingsCLIHandler."]
        self._display_framed_content_block(title, content, footer_text="Naciśnij 0 w SettingsCLIHandler aby wrócić");

    def display_system_resources(self,
                                 cpu_usage: Optional[float], ram_usage: Optional[Dict[str, Any]],
                                 cpu_stats: Optional[Dict[str, Any]], disk_infos: Optional[List[Dict[str, Any]]] = None,
                                 cpu_temps: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                                 rtc_battery_voltage: Optional[str] = None, system_uptime: Optional[str] = None,
                                 load_average: Optional[str] = None, process_count: Optional[int] = None,
                                 network_stats: Optional[Dict[str,str]] = None):
        self.clear_screen(); title = f"{styles.ICON_MONITOR} Monitor Zasobów (Legacy) {styles.ICON_MONITOR}"; content_lines: List[str] = []
        if all(arg is None for arg in [cpu_usage, ram_usage, cpu_stats, disk_infos, cpu_temps, rtc_battery_voltage, system_uptime, load_average, process_count, network_stats]):
            content_lines.append(f"{styles.STYLE_WARNING}Brak informacji o zasobach.{styles.ANSI_RESET}")
        else:
            def add_row_legacy(l:str,v:Any,i:str=""): content_lines.append(f"{styles.STYLE_SYSTEM_MONITOR_LABEL}{i+' ' if i else ''}{l:<22}{styles.ANSI_RESET} {styles.STYLE_SYSTEM_MONITOR_VALUE}{str(v) if v is not None else 'N/A'}{styles.ANSI_RESET}")
            add_row_legacy("Użycie CPU:", f"{cpu_usage:.1f}%" if cpu_usage else "N/A", styles.ICON_CPU)
            if cpu_temps: add_row_legacy("Temp. CPU:", ' | '.join([f"{e.get('label',n).split()[0] if e.get('label') else n.split()[0]}:{e.get('current')}°C" for n,es in cpu_temps.items() for e in es]) or "N/A", "🌡️")
            if ram_usage: add_row_legacy("Użycie RAM:", f"{ram_usage['percent']}% ({ram_usage['used_gb']:.1f}/{ram_usage['total_gb']:.1f}GB)", styles.ICON_RAM)
            if disk_infos: content_lines.append(f"\n{styles.ICON_DISK} Dyski:"); [content_lines.append(f"  {d['mountpoint']} ({d['fstype']}): {d['percent_used']:.1f}%") for d in disk_infos]
        self._display_framed_content_block(title, content_lines, footer_text="Ctrl+C aby wrócić")

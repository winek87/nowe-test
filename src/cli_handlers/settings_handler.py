# src/cli_handlers/settings_handler.py
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Callable
import uuid 
import json 

from ..cli_display import CLIDisplay, MenuOption
from ..config_manager import ConfigManager, DEFAULT_CONFIG
from ..validation.input_validator import InputValidator
from ..logger_configurator import LoggerConfigurator
from ..ffmpeg.ffmpeg_manager import FFmpegManager
from ..profiler import Profiler
from ..repair_profiler import RepairProfiler 
from ..models import RepairProfile 
from .. import cli_styles as styles

try:
    from rich.console import Console
    RICH_FOR_SETTINGS_HANDLER_AVAILABLE = True
except ImportError:
    Console = None # type: ignore
    RICH_FOR_SETTINGS_HANDLER_AVAILABLE = False

logger = logging.getLogger(__name__)

def get_default_from_path(default_dict: Dict, path_list: List[str]) -> Any:
    current = default_dict;
    try:
        for p_part in path_list: current = current[p_part]
        return current
    except (KeyError, TypeError): return None

def full_config_path_for_bool_check(section_key: str, key: str) -> str:
    path_parts = section_key.split('.');
    if key and key.strip(): path_parts.append(key)
    return ".".join(path_parts)

class SettingsCLIHandler:
    def __init__(self, display: CLIDisplay, config_manager: ConfigManager, ffmpeg_manager: FFmpegManager, profiler: Profiler, repair_profiler: RepairProfiler ):
        logger.debug("SettingsCLIHandler: Inicjalizacja rozpoczęta."); self.display = display; self.config_manager = config_manager; self.ffmpeg_manager = ffmpeg_manager; self.profiler = profiler; self.repair_profiler = repair_profiler; self.validator = InputValidator()
        if RICH_FOR_SETTINGS_HANDLER_AVAILABLE and Console is not None: self.rich_console = Console()
        else: self.rich_console = None
        logger.debug("SettingsCLIHandler: Inicjalizacja zakończona.")

    def _save_and_display_config_update(self, section_key: str, key: str, new_value: Any, setting_name_display: str, show_confirmation: bool = True, reload_logging: bool = False):
        action_successful = False
        try:
            old_value_internal = self.config_manager.get_config_value(section_key, key)
            logger.debug(f"SAVE_UPDATE: Odczytano old_value_internal dla '{section_key}.{key}': {old_value_internal} (typ: {type(old_value_internal)})")
            value_to_set_in_config = new_value
            logger.debug(f"SAVE_UPDATE: Przed set_config_value dla '{section_key}.{key}', nowa wartość: {value_to_set_in_config}")
            self.config_manager.set_config_value(section_key, key, value_to_set_in_config)
            current_value_internal = self.config_manager.get_config_value(section_key, key) 
            logger.debug(f"SAVE_UPDATE: Po set_config_value, odczytana current_value_internal dla '{section_key}.{key}': {current_value_internal} (typ: {type(current_value_internal)})")
            if reload_logging or (section_key == "general" and (key in ["log_level_file", "log_level_console", "console_logging_enabled", "clear_log_on_start"])): self._reload_logging_config(show_confirmation_for_reload=False)
            elif section_key == "ffmpeg" and (key in ["ffmpeg_path", "ffprobe_path", "mkvmerge_path"]):
                if hasattr(self.ffmpeg_manager, 'update_tool_paths_from_config'): self.ffmpeg_manager.update_tool_paths_from_config() 
            elif section_key == "paths":
                if key == "profiles_file": self.profiler.profiles_file_path = self.config_manager.get_profiles_file_full_path(); self.profiler.profiles = self.profiler._load_profiles();
                elif key == "repair_profiles_file": self.repair_profiler.profiles_file_path = self.config_manager.get_repair_profiles_file_full_path(); self.repair_profiler.profiles = self.repair_profiler._load_profiles()
            elif section_key == "ui" and key == "progress_bar_width":
                if isinstance(self.display, CLIDisplay) and hasattr(self.display, 'set_progress_bar_width'):
                    try: self.display.set_progress_bar_width(int(current_value_internal))
                    except ValueError: logger.error(f"Nie można ustawić szer. paska: {current_value_internal}")
            action_successful = True
            if show_confirmation:
                old_val_disp = str(old_value_internal); curr_val_disp = str(current_value_internal); full_path_key_check = full_config_path_for_bool_check(section_key, key)
                bool_keys_for_display = ["general.console_logging_enabled", "general.clear_log_on_start", "general.recursive_scan", "processing.delete_original_on_success", "processing.verify_repaired_files", "processing.auto_repair_on_suspicion", "ffmpeg.enable_dynamic_timeout", "processing.repair_options.attempt_sequentially", "processing.repair_options.use_custom_ffmpeg_repair_profiles"]
                strat_base = "processing.repair_options.builtin_strategies_config."; default_builtin_strategies_cfg = DEFAULT_CONFIG.get('processing',{}).get('repair_options',{}).get('builtin_strategies_config',{})
                if default_builtin_strategies_cfg: 
                    for strat_key in default_builtin_strategies_cfg.keys(): bool_keys_for_display.append(f"{strat_base}{strat_key}.enabled")
                if key in ["log_level_file", "log_level_console"] and section_key == "general":
                    old_val_disp = logging.getLevelName(old_value_internal) if isinstance(old_value_internal, int) else str(old_value_internal); curr_val_disp = logging.getLevelName(current_value_internal) if isinstance(current_value_internal, int) else str(current_value_internal)
                elif full_path_key_check in bool_keys_for_display: old_val_disp = "Włączone" if old_value_internal else "Wyłączone"; curr_val_disp = "Włączone" if current_value_internal else "Wyłączone"
                self.display.display_success(f"'{setting_name_display}' zmieniono z '{old_val_disp}' na: '{curr_val_disp}'.")
            logger.info(f"Ustawienie '{full_config_path_for_bool_check(section_key,key)}' zaktualizowane na '{value_to_set_in_config}' (odczytane po zapisie: '{current_value_internal}'). Zapisano.")
        except Exception as e: self.display.display_error(f"Błąd zapisu '{setting_name_display}': {e}"); logger.error(f"Błąd zapisu '{full_config_path_for_bool_check(section_key,key)}': {e}", exc_info=True)
        if show_confirmation or not action_successful: self.display.press_enter_to_continue()

    def _reload_logging_config(self, show_confirmation_for_reload: bool = True):
        log_level_file = self.config_manager.get_config_value('general', 'log_level_file'); log_level_console = self.config_manager.get_config_value('general', 'log_level_console'); console_enabled = self.config_manager.get_config_value('general', 'console_logging_enabled'); clear_log = self.config_manager.get_config_value('general', 'clear_log_on_start'); log_file_path = self.config_manager.get_log_file_full_path() 
        if not isinstance(log_level_file, int): log_level_file = logging.INFO
        if not isinstance(log_level_console, int): log_level_console = logging.INFO
        LoggerConfigurator.setup_logging(log_file=log_file_path, log_level_file=log_level_file,log_level_console=log_level_console, console_logging_enabled=console_enabled,clear_log_on_start=clear_log)
        logger.info("Konfiguracja logowania została przeładowana.")
        if show_confirmation_for_reload: self.display.display_success("Konfiguracja logowania została przeładowana.")

    def _get_bool_display(self, value: bool) -> str:
        tak_char = 'X' if value else ' '; nie_char = 'X' if not value else ' '
        return f"{styles.STYLE_CONFIG_VALUE}[{tak_char}] Tak  |  [{nie_char}] Nie{styles.ANSI_RESET}"

    def _handle_toggle_setting(self, section: str, key: str, display_name: str):
        path_parts = key.split('.'); actual_key = path_parts[-1]; actual_section = section
        if len(path_parts) > 1: actual_section = f"{section}.{'.'.join(path_parts[:-1])}"
        logger.debug(f"SETTINGS_HANDLER (_handle_toggle_setting): Przełączanie dla sekcji '{actual_section}', klucza '{actual_key}' ({display_name})")
        current_val = self.config_manager.get_config_value(actual_section, actual_key, False)
        logger.debug(f"SETTINGS_HANDLER (_handle_toggle_setting): Aktualna wartość odczytana dla '{actual_section}.{actual_key}': {current_val}")
        is_logging_related = section == "general" and key in ["console_logging_enabled", "clear_log_on_start", "log_level_file", "log_level_console"]
        self._save_and_display_config_update(actual_section, actual_key, not current_val, display_name, show_confirmation=True, reload_logging=is_logging_related)
        logger.debug(f"SETTINGS_HANDLER (_handle_toggle_setting): Po zapisie dla {actual_section}.{actual_key}")
        test_val_after_save = self.config_manager.get_config_value(actual_section, actual_key)
        logger.debug(f"SETTINGS_HANDLER (_handle_toggle_setting): Wartość dla '{actual_section}.{actual_key}' PO ZAPISIE (odczytana ponownie): {test_val_after_save}")

    def _handle_choice_setting(self, section: str, key: str, display_name: str, options_map: Dict[str, Any], display_desc_map: Dict[Any, str], last_selected_idx_ref: List[int]):
        current_value = self.config_manager.get_config_value(section, key)
        current_display = display_desc_map.get(current_value, str(current_value))
        self.display.clear_screen(); self.display.display_info(f"Aktualne dla '{display_name}': {styles.STYLE_CONFIG_VALUE}{current_display}{styles.ANSI_RESET}\n")
        menu_choices: List[MenuOption] = []
        for num_choice_key, internal_value_option in options_map.items(): menu_choices.append( (num_choice_key, display_desc_map.get(internal_value_option, str(internal_value_option)), None) )
        menu_choices.append(("q", "Anuluj", styles.ICON_EXIT))
        selected_key, selected_idx = self.display.present_interactive_menu(header_text=f"Zmień: {display_name}", menu_options=menu_choices,prompt_message="Wybierz nową opcję:", allow_numeric_select=True,initial_selection_index=last_selected_idx_ref[0])
        last_selected_idx_ref[0] = selected_idx
        if selected_key and selected_key in options_map: 
            is_logging_related = section == "general" and key in ["log_level_file", "log_level_console"]
            self._save_and_display_config_update(section, key, options_map[selected_key], display_name, True, reload_logging=is_logging_related)
        elif selected_key and selected_key.lower() == 'q': self.display.display_info("Zmiana anulowana.")
        elif selected_key: self.display.display_warning("Nieprawidłowy wybór.")
        if not (selected_key and selected_key in options_map): self.display.press_enter_to_continue()

    def _handle_text_input_setting(self, section: str, key: str, display_name: str, validation_fn: Optional[Callable[[str], Tuple[bool, Any, Optional[str]]]] = None, current_value_transform_fn: Optional[Callable[[Any], str]] = None, is_path: bool = False, path_is_dir: Optional[bool] = None,is_optional: bool = False, default_if_empty: Optional[Any] = None):
        current_value = self.config_manager.get_config_value(section, key); current_value_display = "";
        if current_value is not None: current_value_display = str(current_value.resolve()) if isinstance(current_value, Path) else (current_value_transform_fn(current_value) if current_value_transform_fn else str(current_value))
        else: current_value_display = f"{styles.STYLE_WARNING}Nie ustawiono{styles.ANSI_RESET}"
        self.display.clear_screen(); self.display.display_info(f"Aktualne dla '{display_name}': {styles.STYLE_CONFIG_VALUE}{current_value_display}{styles.ANSI_RESET}\n")
        prompt_suffix = ""; actual_default_for_prompt = default_if_empty if default_if_empty is not None else get_default_from_path(DEFAULT_CONFIG, section.split('.') + [key])
        if is_optional or current_value is None:
            default_display_str = "";
            if isinstance(actual_default_for_prompt, list): default_display_str = ", ".join(map(str, actual_default_for_prompt)) if actual_default_for_prompt else "pustej listy"
            else: default_display_str = str(actual_default_for_prompt) if actual_default_for_prompt is not None else "braku wartości"
            prompt_suffix = f" (zostaw puste, aby użyć: '{default_display_str}')"
            if is_path: prompt_suffix += f" lub '{styles.STYLE_PROMPT}del{styles.ANSI_RESET}' aby usunąć"
        new_value_str = self.display.get_user_choice(f"Nowa wartość dla '{display_name}'{prompt_suffix}: ").strip()
        if not new_value_str:
            if is_optional or current_value is None: self._save_and_display_config_update(section, key, actual_default_for_prompt, display_name, True); return
            else: self.display.display_info("Nie wprowadzono zmian."); self.display.press_enter_to_continue(); return
        if is_path and new_value_str.lower() == 'del': self._save_and_display_config_update(section, key, None, f"Usunięto '{display_name}'", True); return
        final_value_to_set: Any
        if validation_fn:
            is_valid, proc_val, err_msg = validation_fn(new_value_str)
            if not is_valid: self.display.display_error(f"Zła wartość: {err_msg or 'Błąd walidacji.'}"); self.display.press_enter_to_continue(); return
            final_value_to_set = proc_val
        elif is_path:
            is_v_path, res_path, p_err_msg = self.validator.is_valid_path(new_value_str, False)
            if not is_v_path or not res_path: self.display.display_error(f"Zła ścieżka: {p_err_msg or 'Błąd'}"); self.display.press_enter_to_continue(); return
            if path_is_dir: 
                try: res_path.mkdir(parents=True, exist_ok=True)
                except OSError as e: self.display.display_error(f"Nie można utworzyć kat. '{res_path}': {e}"); self.display.press_enter_to_continue(); return
            final_value_to_set = res_path
        else: final_value_to_set = new_value_str
        self._save_and_display_config_update(section, key, final_value_to_set, display_name, True)
            
    def _handle_numeric_input_setting(self, section: str, key: str, display_name: str, data_type: type = int, min_val: Optional[Union[int, float]] = None, max_val: Optional[Union[int, float]] = None, special_meaning_val: Optional[Any]=None, special_meaning_desc: Optional[str]=None):
        current_value = self.config_manager.get_config_value(section,key); current_display = str(special_meaning_desc or special_meaning_val) if special_meaning_val is not None and current_value == special_meaning_val else str(current_value)
        self.display.clear_screen(); self.display.display_info(f"Aktualna dla '{display_name}': {styles.STYLE_CONFIG_VALUE}{current_display}{styles.ANSI_RESET}\n")
        prompt_parts = [f"Podaj nową wartość ({data_type.__name__}"];
        if min_val is not None: prompt_parts.append(f"min: {min_val}")
        if max_val is not None: prompt_parts.append(f"max: {max_val}")
        if special_meaning_val is not None and special_meaning_desc: prompt_parts.append(f"'{special_meaning_val}'={special_meaning_desc}")
        prompt_msg = ", ".join(prompt_parts) + "): "; input_str = self.display.get_user_choice(prompt_msg).strip()
        if not input_str: self.display.display_info("Nie wprowadzono zmian."); self.display.press_enter_to_continue(); return
        if special_meaning_val is not None and input_str == str(special_meaning_val): self._save_and_display_config_update(section,key, special_meaning_val, display_name, True); return
        try:
            new_value = data_type(input_str)
            if (min_val is not None and new_value < min_val) or (max_val is not None and new_value > max_val): self.display.display_error(f"Wartość '{new_value}' poza zakresem.")
            else: self._save_and_display_config_update(section,key,new_value, display_name, True)
        except ValueError: self.display.display_error(f"Zły format liczby: '{input_str}'.")
        self.display.press_enter_to_continue()

    def manage_settings_menu(self):
        menu_title = f"{styles.ICON_SETTINGS} Główne Menu Ustawień"; last_selected_category_idx = 0
        while True:
            desc_style = styles.STYLE_MENU_DESCRIPTION
            menu_options: List[MenuOption] = [("1", f"Ustawienia Ogólne {desc_style}- Skanowanie, logi podstawowe{styles.ANSI_RESET}", styles.ICON_SETTINGS),("2", f"Ustawienia Przetwarzania {desc_style}- Błędy, konflikty, wzorce nazw{styles.ANSI_RESET}", styles.ICON_REPAIR),("3", f"Ustawienia Naprawy Plików {desc_style}- Strategie i kolejność naprawy{styles.ANSI_RESET}", styles.ICON_REPAIR),("4", f"Zarządzaj Profilami Naprawy FFmpeg {desc_style}- Twórz i edytuj profile naprawy FFmpeg{styles.ANSI_RESET}", styles.ICON_PROFILE),("5", f"Ustawienia Ścieżek i Rozszerzeń {desc_style}- Katalogi, typy plików{styles.ANSI_RESET}", styles.ICON_FOLDER_SCAN),("6", f"Ustawienia Narzędzi CLI {desc_style}- Ścieżki FFmpeg, mkvmerge, limity czasu{styles.ANSI_RESET}", styles.ICON_PLAY),("7", f"Konfiguracja Globalna {desc_style}- Zapis/odczyt pliku config.yaml{styles.ANSI_RESET}", styles.ICON_SAVE),("0", "Powrót do Menu Głównego", styles.ICON_EXIT)]
            choice_key, last_selected_category_idx = self.display.present_interactive_menu(header_text=menu_title, menu_options=menu_options,prompt_message="Wybierz kategorię ustawień:", allow_numeric_select=True,initial_selection_index=last_selected_category_idx)
            if choice_key == '0': break
            elif choice_key == '1': self._handle_general_settings_submenu()
            elif choice_key == '2': self._handle_processing_settings_submenu()
            elif choice_key == '3': self._handle_repair_settings_submenu()
            elif choice_key == '4': self._manage_ffmpeg_repair_profiles_menu()
            elif choice_key == '5': self._handle_paths_extensions_submenu()
            elif choice_key == '6': self._handle_cli_tools_settings_submenu()
            elif choice_key == '7': self._handle_load_save_config_submenu()
            else: self.display.display_warning("Nieprawidłowy wybór kategorii."); self.display.press_enter_to_continue(); last_selected_category_idx = 0
    
    def _handle_general_settings_submenu(self):
        menu_title = f"{styles.ICON_SETTINGS} Ustawienia Ogólne"; desc_style = styles.STYLE_MENU_DESCRIPTION; last_idx = 0
        while True:
            rec_scan_val = self.config_manager.get_config_value('general', 'recursive_scan'); auto_repair_val = self.config_manager.get_config_value('processing', 'auto_repair_on_suspicion'); clear_log_val = self.config_manager.get_config_value('general', 'clear_log_on_start'); console_log_val = self.config_manager.get_config_value('general', 'console_logging_enabled'); log_level_file_val = self.config_manager.get_config_value('general', 'log_level_file'); log_level_console_val = self.config_manager.get_config_value('general', 'log_level_console')
            log_level_display_map_with_desc = { logging.DEBUG: "DEBUG (Szczegółowe)", logging.INFO: "INFO (Standardowe)", logging.WARNING: "WARNING (Ostrzeżenia)", logging.ERROR: "ERROR (Błędy)", logging.CRITICAL: "CRITICAL (Krytyczne)"}
            options: List[MenuOption] = [("1", f"Skanowanie rekursywne: {self._get_bool_display(rec_scan_val)} {desc_style}- Skanuj także podkatalogi?{styles.ANSI_RESET}", styles.ICON_FOLDER_SCAN),("2", f"Auto-naprawa przed transk.: {self._get_bool_display(auto_repair_val)} {desc_style}- Automatyczna próba naprawy.{styles.ANSI_RESET}", styles.ICON_REPAIR),("3", f"Czyść log przy starcie: {self._get_bool_display(clear_log_val)} {desc_style}- Kasować plik logu przy uruchomieniu?{styles.ANSI_RESET}", styles.ICON_LOG),("4", f"Logowanie na konsoli: {self._get_bool_display(console_log_val)} {desc_style}- Pokazuj logi także w konsoli?{styles.ANSI_RESET}", styles.ICON_LOG),("5", f"Poziom log. (plik): {styles.STYLE_CONFIG_VALUE}{log_level_display_map_with_desc.get(log_level_file_val, str(log_level_file_val))}{styles.ANSI_RESET} {desc_style}- Szczegółowość logów w pliku.{styles.ANSI_RESET}", None),("6", f"Poziom log. (konsola): {styles.STYLE_CONFIG_VALUE}{log_level_display_map_with_desc.get(log_level_console_val, str(log_level_console_val))}{styles.ANSI_RESET} {desc_style}- Szczegółowość logów w konsoli.{styles.ANSI_RESET}", None),("0", "Powrót", styles.ICON_EXIT)]
            choice, last_idx = self.display.present_interactive_menu(menu_title, options, "Wybierz opcję:", initial_selection_index=last_idx)
            if choice == '0': break
            elif choice == '1': self._handle_toggle_setting('general', 'recursive_scan', "Skanowanie rekursywne")
            elif choice == '2': self._handle_toggle_setting('processing', 'auto_repair_on_suspicion', "Automatyczna naprawa")
            elif choice == '3': self._handle_toggle_setting('general', 'clear_log_on_start', "Czyszczenie logu")
            elif choice == '4': self._handle_toggle_setting('general', 'console_logging_enabled', "Logowanie na konsoli")
            elif choice == '5': self._handle_specific_logging_level('log_level_file', "Poziom logowania (plik)", [last_idx])
            elif choice == '6': self._handle_specific_logging_level('log_level_console', "Poziom logowania (konsola)", [last_idx])
            else: self.display.display_warning("Nieznana opcja.")

    def _handle_processing_settings_submenu(self):
        menu_title = f"{styles.ICON_REPAIR} Ustawienia Przetwarzania"; desc_style = styles.STYLE_MENU_DESCRIPTION; last_idx = 0
        while True:
            del_orig = self.config_manager.get_config_value('processing', 'delete_original_on_success'); verify_rep = self.config_manager.get_config_value('processing', 'verify_repaired_files'); error_h = self.config_manager.get_config_value('processing', 'error_handling'); err_map = {'skip':'Pomiń plik','stop':'Zatrzymaj'}; conflict = self.config_manager.get_config_value('processing', 'output_file_exists'); conf_map = {'skip':'Pomiń','overwrite':'Nadpisz','rename':'Zmień nazwę'}; rename_p = self.config_manager.get_config_value('processing', 'rename_pattern'); repair_p = self.config_manager.get_config_value('processing', 'repair_rename_pattern')
            options: List[MenuOption] = [("1", f"Usuwaj oryginał po sukcesie: {self._get_bool_display(del_orig)} {desc_style}({styles.STYLE_WARNING}OSTROŻNIE!{styles.ANSI_RESET}){styles.ANSI_RESET}", styles.ICON_DELETE),("2", f"Weryfikuj naprawione pliki: {self._get_bool_display(verify_rep)} {desc_style}- Sprawdź plik po naprawie.{styles.ANSI_RESET}", styles.ICON_SUCCESS),("3", f"Obsługa błędów transkod.: {styles.STYLE_CONFIG_VALUE}{err_map.get(error_h,error_h)}{styles.ANSI_RESET} {desc_style}- Reakcja na błąd pliku.{styles.ANSI_RESET}", styles.ICON_WARNING),("4", f"Konflikt nazw plików wyj.: {styles.STYLE_CONFIG_VALUE}{conf_map.get(conflict,conflict)}{styles.ANSI_RESET} {desc_style}- Gdy plik wyjściowy istnieje.{styles.ANSI_RESET}", styles.ICON_SETTINGS),("5", f"Wzorzec nazwy (konflikt): '{styles.STYLE_CONFIG_VALUE}{rename_p}{styles.ANSI_RESET}' {desc_style}- Dla opcji 'Zmień nazwę'.{styles.ANSI_RESET}", styles.ICON_SETTINGS),("6", f"Wzorzec nazwy (naprawa): '{styles.STYLE_CONFIG_VALUE}{repair_p}{styles.ANSI_RESET}' {desc_style}- Dla naprawionych plików.{styles.ANSI_RESET}", styles.ICON_SETTINGS),("0", "Powrót", styles.ICON_EXIT)]
            choice, last_idx = self.display.present_interactive_menu(menu_title, options, "Wybierz opcję:", initial_selection_index=last_idx)
            if choice == '0': break
            elif choice == '1': self._handle_toggle_setting('processing', 'delete_original_on_success', "Usuwanie oryginału")
            elif choice == '2': self._handle_toggle_setting('processing', 'verify_repaired_files', "Weryfikacja naprawionych")
            elif choice == '3': self._handle_error_handling_setting([last_idx])
            elif choice == '4': self._handle_output_file_exists_action([last_idx])
            elif choice == '5': self._handle_text_input_setting('processing', 'rename_pattern', "Wzorzec dla konfliktu", default_if_empty=DEFAULT_CONFIG['processing']['rename_pattern'])
            elif choice == '6': self._handle_text_input_setting('processing', 'repair_rename_pattern', "Wzorzec dla naprawy", default_if_empty=DEFAULT_CONFIG['processing']['repair_rename_pattern'])
            else: self.display.display_warning("Nieznana opcja.")
    
    def _handle_repair_settings_submenu(self):
        menu_title = f"{styles.ICON_REPAIR} Ustawienia Naprawy Plików"; desc_style = styles.STYLE_MENU_DESCRIPTION
        base_path = 'processing.repair_options'; last_idx = 0
        while True:
            logger.debug(f"SETTINGS_HANDLER: _handle_repair_settings_submenu - POCZĄTEK PĘTLI, odczyt wartości dla menu.")
            attempt_seq = self.config_manager.get_config_value(base_path, 'attempt_sequentially')
            use_custom_profiles = self.config_manager.get_config_value(base_path, 'use_custom_ffmpeg_repair_profiles')
            defined_builtin_strategies = DEFAULT_CONFIG.get('processing', {}).get('repair_options', {}).get('builtin_strategies_config', {})
            
            menu_options: List[MenuOption] = [
                ("1", f"Próbuj naprawiać sekwencyjnie: {self._get_bool_display(attempt_seq)} {desc_style}- Próbuj kolejnych włączonych strategii/profili.{styles.ANSI_RESET}", styles.ICON_SETTINGS),
                ("2", f"Używaj niestandardowych profili FFmpeg: {self._get_bool_display(use_custom_profiles)} {desc_style}- Uwzględnij profile z 'Zarządzaj Profilami...'.{styles.ANSI_RESET}", styles.ICON_PROFILE)
            ]
            current_option_number = 3
            builtin_strategy_keys_to_display = list(defined_builtin_strategies.keys())

            for strategy_key in builtin_strategy_keys_to_display:
                strat_default_details = defined_builtin_strategies[strategy_key]
                config_enabled_relative_key = f"builtin_strategies_config.{strategy_key}.enabled" 
                # Dodatkowe logowanie PRZED get_config_value
                logger.debug(f"SETTINGS_HANDLER (Menu Display): PRZED get_config_value dla '{base_path}.{config_enabled_relative_key}'")
                try:
                    # Logowanie bezpośredniego dostępu do self.config_manager._config
                    # To może być ryzykowne, jeśli struktura nie istnieje, więc w bloku try-except
                    temp_direct_val = self.config_manager._config['processing']['repair_options']['builtin_strategies_config'][strategy_key]['enabled']
                    logger.debug(f"SETTINGS_HANDLER (Menu Display): Bezpośredni odczyt z _config dla '{strategy_key}.enabled': {temp_direct_val}")
                except KeyError:
                    logger.debug(f"SETTINGS_HANDLER (Menu Display): Klucz dla '{strategy_key}.enabled' NIE ISTNIEJE w self.config_manager._config")
                except Exception as e_dbg:
                    logger.error(f"SETTINGS_HANDLER (Menu Display): Błąd przy bezpośrednim logowaniu _config: {e_dbg}")

                is_enabled = self.config_manager.get_config_value(base_path, config_enabled_relative_key, default=strat_default_details.get('enabled', False))
                logger.debug(f"SETTINGS_HANDLER (Menu Display): PO get_config_value dla '{strategy_key}', klucz='{base_path}.{config_enabled_relative_key}', odczytano is_enabled: {is_enabled} (Typ: {type(is_enabled)})")
                
                name = strat_default_details.get('name', strategy_key); description = strat_default_details.get('description', 'Brak opisu.')
                menu_options.append((str(current_option_number), f"{name} (wbudowana): {self._get_bool_display(is_enabled)} {desc_style}- {description}{styles.ANSI_RESET}", styles.ICON_REPAIR)); current_option_number +=1
            
            if use_custom_profiles:
                ffmpeg_repair_profiles = self.repair_profiler.get_all_profiles(); enabled_profile_ids = self.config_manager.get_config_value(base_path, 'enabled_ffmpeg_profile_ids', [])
                if ffmpeg_repair_profiles:
                    menu_options.append(("", f"{desc_style}--- Niestandardowe Profile Naprawy FFmpeg (Włącz/Wyłącz) ---{styles.ANSI_RESET}", None))
                    for profile in ffmpeg_repair_profiles:
                        is_profile_enabled = str(profile.id) in enabled_profile_ids; profile_menu_key = f"profile_{str(profile.id)}"
                        logger.debug(f"SETTINGS_HANDLER (Menu Display): Dla profilu FFmpeg '{profile.name}' (ID: {profile.id}), odczytano is_profile_enabled: {is_profile_enabled}")
                        menu_options.append((profile_menu_key, f"{profile.name}: {self._get_bool_display(is_profile_enabled)} {desc_style}- {profile.description[:30].strip()}...{styles.ANSI_RESET}", styles.ICON_PROFILE))
            
            menu_options.append(("0", "Powrót", styles.ICON_EXIT))
            choice, last_idx = self.display.present_interactive_menu(menu_title, menu_options, "Wybierz opcję:", initial_selection_index=last_idx)
            logger.debug(f"SETTINGS_HANDLER: _handle_repair_settings_submenu - Użytkownik wybrał: {choice}")
            
            if choice == '0': break
            elif choice == '1': self._handle_toggle_setting(base_path, 'attempt_sequentially', "Naprawa sekwencyjna")
            elif choice == '2': self._handle_toggle_setting(base_path, 'use_custom_ffmpeg_repair_profiles', "Używanie niestandardowych profili FFmpeg")
            elif choice.startswith("profile_"): 
                profile_id_to_toggle = choice.replace("profile_", ""); enabled_ids: List[str] = list(self.config_manager.get_config_value(base_path, 'enabled_ffmpeg_profile_ids', [])); profile_obj = self.repair_profiler.get_profile_by_id(profile_id_to_toggle); profile_name_disp = profile_obj.name if profile_obj else f"Profil ID: {profile_id_to_toggle}"
                if profile_id_to_toggle in enabled_ids: enabled_ids.remove(profile_id_to_toggle)
                else: enabled_ids.append(profile_id_to_toggle)
                self._save_and_display_config_update(base_path, 'enabled_ffmpeg_profile_ids', enabled_ids, f"Stan profilu FFmpeg: {profile_name_disp}", show_confirmation=True)
            else: 
                try:
                    choice_as_int = int(choice); option_number_offset = 3 ; selected_option_index = choice_as_int - option_number_offset
                    if 0 <= selected_option_index < len(builtin_strategy_keys_to_display):
                        chosen_strategy_key = builtin_strategy_keys_to_display[selected_option_index]
                        key_for_toggle = f"builtin_strategies_config.{chosen_strategy_key}.enabled"
                        strategy_name_for_display = defined_builtin_strategies[chosen_strategy_key].get('name', chosen_strategy_key)
                        logger.debug(f"SETTINGS_HANDLER: Wybrano przełączenie wbudowanej strategii: {chosen_strategy_key} (klucz do toggle: {key_for_toggle})")
                        self._handle_toggle_setting(base_path, key_for_toggle, f"Strategia wbudowana: {strategy_name_for_display}")
                    else: self.display.display_warning("Nieprawidłowy wybór strategii.")
                except ValueError:
                    if not choice.startswith("profile_"): self.display.display_warning("Nieprawidłowy wybór.")
            test_mkv_remux_after_action = self.config_manager.get_config_value('processing.repair_options', 'builtin_strategies_config.mkvmerge_remux.enabled', default="BŁĄD_ODCZYTU_TESTOWEGO_PO_AKCJI")
            logger.debug(f"SETTINGS_HANDLER: _handle_repair_settings_submenu - Koniec obsługi wyboru '{choice}'. Testowy odczyt 'mkvmerge_remux.enabled': {test_mkv_remux_after_action}")

    def _manage_ffmpeg_repair_profiles_menu(self):
        menu_title = f"{styles.ICON_PROFILE} Zarządzaj Profilami Naprawy FFmpeg"; last_idx = 0
        while True:
            menu_options: List[MenuOption] = [("1", "Wyświetl listę profili naprawy FFmpeg", styles.ICON_LIST),("2", "Dodaj nowy profil naprawy FFmpeg", styles.ICON_PLAY),("3", "Edytuj istniejący profil naprawy FFmpeg", styles.ICON_SETTINGS),("4", "Usuń profil naprawy FFmpeg", styles.ICON_DELETE),("0", "Powrót do Głównego Menu Ustawień", styles.ICON_EXIT)]
            choice, last_idx = self.display.present_interactive_menu(menu_title, menu_options, "Wybierz opcję:", initial_selection_index=last_idx, allow_numeric_select=True)
            if choice == '0': break
            elif choice == '1': self._list_ffmpeg_repair_profiles()
            elif choice == '2': self._add_new_ffmpeg_repair_profile()
            elif choice == '3': self._edit_ffmpeg_repair_profile()
            elif choice == '4': self._delete_ffmpeg_repair_profile()
            else: self.display.display_warning("Nieznana opcja.")

    def _get_repair_profile_data_from_user(self, existing_profile: Optional[RepairProfile] = None) -> Optional[RepairProfile]:
        self.display.clear_screen(); profile_id = existing_profile.id if existing_profile else uuid.uuid4(); header_msg = f"Edycja Profilu Naprawy: {existing_profile.name}" if existing_profile else "Dodawanie Nowego Profilu Naprawy FFmpeg"; self.display.display_header(header_msg)
        name_prompt = f"Nazwa profilu (zostaw puste, aby zachować '{existing_profile.name if existing_profile else ''}'): " if existing_profile else "Nazwa profilu naprawy: "; name = self.display.get_user_choice(name_prompt).strip()
        if existing_profile and not name: name = existing_profile.name
        elif not name: self.display.display_warning("Nazwa nie może być pusta."); self.display.press_enter_to_continue(); return None
        desc_prompt = f"Opis (zostaw puste, aby zachować '{existing_profile.description if existing_profile else ''}'): " if existing_profile else "Opis profilu (opcjonalnie): "; description = self.display.get_user_choice(desc_prompt).strip()
        if existing_profile and not description: description = existing_profile.description
        default_params_str = ' '.join(existing_profile.ffmpeg_params) if existing_profile else "-c copy -map_metadata 0 -map_chapters 0 -map 0 -ignore_unknown"; params_prompt = f"Parametry FFmpeg (zostaw puste, aby zachować '{default_params_str}'): " if existing_profile else f"Parametry FFmpeg (np. {default_params_str}): "; ffmpeg_params_str = self.display.get_user_choice(params_prompt).strip()
        ffmpeg_params = ffmpeg_params_str.split() if ffmpeg_params_str else (existing_profile.ffmpeg_params if existing_profile else default_params_str.split())
        if not ffmpeg_params: self.display.display_warning("Parametry nie mogą być puste."); self.display.press_enter_to_continue(); return None
        default_mkv_only = existing_profile.applies_to_mkv_only if existing_profile else False; mkv_only_disp = 'Tak' if default_mkv_only else 'Nie'; mkv_only_prompt = f"Tylko dla MKV? (Tak/Nie) [Aktualnie: {mkv_only_disp}]: " if existing_profile else "Czy profil ma być stosowany tylko do plików MKV? (Tak/Nie) [Nie]: "; applies_to_mkv_only_str = self.display.get_user_choice(mkv_only_prompt).lower(); applies_to_mkv_only = default_mkv_only
        if applies_to_mkv_only_str == 'tak': applies_to_mkv_only = True
        elif applies_to_mkv_only_str == 'nie': applies_to_mkv_only = False
        default_copy_tags = existing_profile.copy_tags if existing_profile else True; copy_tags_disp = 'Tak' if default_copy_tags else 'Nie'; copy_tags_prompt = f"Kopiować tagi? (Tak/Nie) [Aktualnie: {copy_tags_disp}]: " if existing_profile else "Czy kopiować tagi z pliku źródłowego? (Tak/Nie) [Tak]: "; copy_tags_str = self.display.get_user_choice(copy_tags_prompt).lower(); copy_tags = default_copy_tags
        if copy_tags_str == 'tak': copy_tags = True
        elif copy_tags_str == 'nie': copy_tags = False
        return RepairProfile(id=profile_id, name=name, description=description, ffmpeg_params=ffmpeg_params, applies_to_mkv_only=applies_to_mkv_only, copy_tags=copy_tags)

    def _list_ffmpeg_repair_profiles(self, for_selection: bool = False) -> Optional[List[RepairProfile]]:
        self.display.clear_screen(); self.display.display_header(f"{styles.ICON_LIST} Lista Profili Naprawy FFmpeg"); profiles = self.repair_profiler.get_all_profiles()
        if not profiles: self.display.display_info("Brak zdefiniowanych profili naprawy FFmpeg.")
        else:
            for i, profile in enumerate(profiles):
                params_preview = ' '.join(profile.ffmpeg_params)[:60] + ("..." if len(' '.join(profile.ffmpeg_params)) > 60 else ""); mkv_only = f" {styles.STYLE_WARNING}(Tylko MKV){styles.ANSI_RESET}" if profile.applies_to_mkv_only else ""; tags = f" {styles.STYLE_INFO}(Kopiuj tagi){styles.ANSI_RESET}" if profile.copy_tags else f" {styles.STYLE_MENU_DESCRIPTION}(Nie kopiuj tagów){styles.ANSI_RESET}"
                self.display.display_info(f"{i + 1}. {styles.STYLE_PROMPT}{profile.name}{styles.ANSI_RESET}{mkv_only}{tags}"); self.display.display_message(f"   Opis: {styles.STYLE_MENU_DESCRIPTION}{profile.description or 'Brak'}{styles.ANSI_RESET}"); self.display.display_message(f"   Parametry: {styles.STYLE_CONFIG_VALUE}{params_preview}{styles.ANSI_RESET}")
                if i < len(profiles) - 1: self.display.display_separator(length=40)
        if for_selection: return profiles
        self.display.press_enter_to_continue(); return None
        
    def _add_new_ffmpeg_repair_profile(self):
        profile_data = self._get_repair_profile_data_from_user()
        if profile_data:
            try: self.repair_profiler.add_profile(profile_data); self.display.display_success(f"Profil naprawy '{profile_data.name}' dodany.")
            except ValueError as e: self.display.display_error(f"Błąd: {e}")
            except Exception as e: self.display.display_error(f"Nieoczekiwany błąd: {e}"); logger.error("Błąd w _add_new_ffmpeg_repair_profile", exc_info=True)
        else: self.display.display_warning("Anulowano dodawanie.")
        self.display.press_enter_to_continue()

    def _select_ffmpeg_repair_profile_for_action(self, action_name: str) -> Optional[RepairProfile]:
        profiles = self.repair_profiler.get_all_profiles();
        if not profiles: self.display.display_info(f"Brak profili naprawy do {action_name}."); self.display.press_enter_to_continue(); return None
        self.display.clear_screen(); self._list_ffmpeg_repair_profiles(for_selection=True); self.display.display_separator()
        menu_options: List[MenuOption] = [(str(p.id), f"{i+1}. {p.name}", styles.ICON_PROFILE) for i, p in enumerate(profiles)]; menu_options.append(("q", "Anuluj", styles.ICON_EXIT))
        choice_id_str, _ = self.display.present_interactive_menu(header_text=f"Wybierz profil naprawy do {action_name}", menu_options=menu_options, prompt_message="Wybierz profil:", allow_numeric_select=False, initial_selection_index=0)
        if choice_id_str and choice_id_str.lower() != 'q': return self.repair_profiler.get_profile_by_id(choice_id_str)
        self.display.display_info(f"Anulowano {action_name} profilu."); return None

    def _edit_ffmpeg_repair_profile(self):
        profile_to_edit = self._select_ffmpeg_repair_profile_for_action("edycji");
        if not profile_to_edit: return 
        updated_data = self._get_repair_profile_data_from_user(existing_profile=profile_to_edit)
        if updated_data:
            try: self.repair_profiler.update_profile(updated_data); self.display.display_success(f"Profil '{updated_data.name}' zaktualizowany.")
            except ValueError as e: self.display.display_error(f"Błąd: {e}")
            except Exception as e: self.display.display_error(f"Nieoczekiwany błąd: {e}"); logger.error("Błąd w _edit_ffmpeg_repair_profile", exc_info=True)
        else: self.display.display_warning("Anulowano edycję.")
        self.display.press_enter_to_continue()

    def _delete_ffmpeg_repair_profile(self):
        profile_to_delete = self._select_ffmpeg_repair_profile_for_action("usunięcia");
        if not profile_to_delete: return
        confirm = self.display.get_user_choice(f"Na pewno usunąć profil '{profile_to_delete.name}'? (tak/nie): ").lower()
        if confirm == 'tak':
            if self.repair_profiler.delete_profile(str(profile_to_delete.id)): self.display.display_success(f"Profil '{profile_to_delete.name}' usunięty.")
            else: self.display.display_error("Nie udało się usunąć profilu.")
        else: self.display.display_info("Anulowano usuwanie.")
        self.display.press_enter_to_continue()

    def _handle_paths_extensions_submenu(self):
        menu_title = f"{styles.ICON_FOLDER_SCAN} Ścieżki i Rozszerzenia"; desc_style = styles.STYLE_MENU_DESCRIPTION; last_idx = 0
        while True:
            out_dir_trans = str(self.config_manager.get_config_value('paths', 'default_output_directory')); out_dir_rep = str(self.config_manager.get_config_value('paths', 'default_repaired_directory')); job_state_dir = str(self.config_manager.get_config_value('paths', 'job_state_dir')); log_file_rel = str(self.config_manager.get_config_value('paths', 'log_file')); profiles_rel = str(self.config_manager.get_config_value('paths', 'profiles_file')); repair_profiles_rel = str(self.config_manager.get_config_value('paths', 'repair_profiles_file')); exts_list = self.config_manager.get_config_value('processing','supported_file_extensions',[]); exts_disp = ", ".join(exts_list) if exts_list else "Wszystkie"
            options: List[MenuOption] = [("1", f"Kat. transkod.: {styles.STYLE_CONFIG_VALUE}{out_dir_trans}{styles.ANSI_RESET} {desc_style}- Domyślny katalog.{styles.ANSI_RESET}", styles.ICON_FOLDER_SCAN),("2", f"Kat. napraw.: {styles.STYLE_CONFIG_VALUE}{out_dir_rep}{styles.ANSI_RESET} {desc_style}- Domyślny katalog.{styles.ANSI_RESET}", styles.ICON_REPAIR),("3", f"Kat. danych aplikacji: {styles.STYLE_CONFIG_VALUE}{job_state_dir}{styles.ANSI_RESET} {desc_style}- Stany zadań itp.{styles.ANSI_RESET}", styles.ICON_SAVE),("4", f"Plik logu (wzgl.): {styles.STYLE_CONFIG_VALUE}{log_file_rel}{styles.ANSI_RESET} {desc_style}- Nazwa pliku logu.{styles.ANSI_RESET}", styles.ICON_LOG),("5", f"Plik profili kodow. (wzgl.): {styles.STYLE_CONFIG_VALUE}{profiles_rel}{styles.ANSI_RESET} {desc_style}- Profile kodowania.{styles.ANSI_RESET}", styles.ICON_PROFILE),("6", f"Plik profili napr. (wzgl.): {styles.STYLE_CONFIG_VALUE}{repair_profiles_rel}{styles.ANSI_RESET} {desc_style}- Profile naprawy FFmpeg.{styles.ANSI_RESET}", styles.ICON_PROFILE),("7", f"Obsługiwane rozszerzenia: {styles.STYLE_CONFIG_VALUE}{exts_disp}{styles.ANSI_RESET} {desc_style}- Filtruj pliki.{styles.ANSI_RESET}", styles.ICON_LIST),("0", "Powrót", styles.ICON_EXIT)]
            choice, last_idx = self.display.present_interactive_menu(menu_title, options, "Wybierz opcję (Zmień):", initial_selection_index=last_idx)
            if choice == '0': break
            elif choice == '1': self._handle_text_input_setting('paths', 'default_output_directory', "Katalog dla transkodowanych", is_path=True, path_is_dir=True)
            elif choice == '2': self._handle_text_input_setting('paths', 'default_repaired_directory', "Katalog dla naprawionych", is_path=True, path_is_dir=True)
            elif choice == '3': self._handle_text_input_setting('paths', 'job_state_dir', "Katalog danych aplikacji", is_path=True, path_is_dir=True)
            elif choice == '4': self._handle_text_input_setting('paths', 'log_file', "Plik logu (wzgl. kat. danych)", is_path=False)
            elif choice == '5': self._handle_text_input_setting('paths', 'profiles_file', "Plik profili kodowania (wzgl. kat. config)", is_path=False)
            elif choice == '6': self._handle_text_input_setting('paths', 'repair_profiles_file', "Plik profili naprawy (wzgl. kat. config)", is_path=False)
            elif choice == '7': self._handle_supported_extensions()
            else: self.display.display_warning("Nieznana opcja.")
    def _handle_cli_tools_settings_submenu(self):
        menu_title = f"{styles.ICON_PLAY} Ustawienia Narzędzi CLI"; desc_style = styles.STYLE_MENU_DESCRIPTION; last_idx = 0
        while True:
            ffmpeg_p = str(self.config_manager.get_config_value('ffmpeg', 'ffmpeg_path', 'ffmpeg')); ffprobe_p = str(self.config_manager.get_config_value('ffmpeg', 'ffprobe_path', 'ffprobe')); mkvmerge_p = str(self.config_manager.get_config_value('ffmpeg', 'mkvmerge_path', 'mkvmerge')); enable_dyn_timeout = self.config_manager.get_config_value('ffmpeg', 'enable_dynamic_timeout'); dyn_multi = self.config_manager.get_config_value('ffmpeg', 'dynamic_timeout_multiplier'); dyn_buffer = self.config_manager.get_config_value('ffmpeg', 'dynamic_timeout_buffer_seconds'); dyn_min = self.config_manager.get_config_value('ffmpeg', 'dynamic_timeout_min_seconds'); fixed_timeout = self.config_manager.get_config_value('ffmpeg', 'fixed_timeout_seconds'); fixed_timeout_disp = f"{fixed_timeout}s" if fixed_timeout != 0 else "Bez limitu"
            options: List[MenuOption] = [("1", f"Ścieżka FFmpeg: {styles.STYLE_CONFIG_VALUE}{ffmpeg_p}{styles.ANSI_RESET} {desc_style}- Nazwa lub pełna ścieżka.{styles.ANSI_RESET}", styles.ICON_SETTINGS),("2", f"Ścieżka FFprobe: {styles.STYLE_CONFIG_VALUE}{ffprobe_p}{styles.ANSI_RESET} {desc_style}- Nazwa lub pełna ścieżka.{styles.ANSI_RESET}", styles.ICON_SETTINGS),("3", f"Ścieżka mkvmerge: {styles.STYLE_CONFIG_VALUE}{mkvmerge_p}{styles.ANSI_RESET} {desc_style}- Nazwa lub pełna ścieżka.{styles.ANSI_RESET}", styles.ICON_SETTINGS),("4", f"Dynamiczny timeout transkod.: {self._get_bool_display(enable_dyn_timeout)} {desc_style}- Obliczany na podst. długości pliku.{styles.ANSI_RESET}", styles.ICON_TIME_ETA),("5", f"  Mnożnik dynamic. timeoutu: {styles.STYLE_CONFIG_VALUE}{dyn_multi:.1f}x{styles.ANSI_RESET}", None),("6", f"  Bufor dynamic. timeoutu: {styles.STYLE_CONFIG_VALUE}{dyn_buffer}s{styles.ANSI_RESET}", None),("7", f"  Min. dynamiczny timeout: {styles.STYLE_CONFIG_VALUE}{dyn_min}s{styles.ANSI_RESET}", None),("8", f"Stały timeout transkod.: {styles.STYLE_CONFIG_VALUE}{fixed_timeout_disp}{styles.ANSI_RESET} {desc_style}(0=bez limitu){styles.ANSI_RESET}", styles.ICON_TIME_ETA),("0", "Powrót", styles.ICON_EXIT)]
            choice, last_idx = self.display.present_interactive_menu(menu_title, options, "Wybierz opcję (Zmień):", initial_selection_index=last_idx)
            if choice == '0': break
            elif choice == '1': self._handle_text_input_setting('ffmpeg', 'ffmpeg_path', "Ścieżka FFmpeg", is_path=False)
            elif choice == '2': self._handle_text_input_setting('ffmpeg', 'ffprobe_path', "Ścieżka FFprobe", is_path=False)
            elif choice == '3': self._handle_text_input_setting('ffmpeg', 'mkvmerge_path', "Ścieżka mkvmerge", is_path=False)
            elif choice == '4': self._handle_toggle_setting('ffmpeg', 'enable_dynamic_timeout', "Dynamiczny timeout")
            elif choice == '5': self._handle_numeric_input_setting('ffmpeg', 'dynamic_timeout_multiplier', "Mnożnik dyn. timeoutu", float, 0.1, 20.0)
            elif choice == '6': self._handle_numeric_input_setting('ffmpeg', 'dynamic_timeout_buffer_seconds', "Bufor dyn. timeoutu (s)", int, 0)
            elif choice == '7': self._handle_numeric_input_setting('ffmpeg', 'dynamic_timeout_min_seconds', "Min. dyn. timeout (s)", int, 10)
            elif choice == '8': self._handle_numeric_input_setting('ffmpeg', 'fixed_timeout_seconds', "Stały timeout (s)", int, 0, special_meaning_val=0, special_meaning_desc="Bez limitu")
            else: self.display.display_warning("Nieznana opcja.")
    def _handle_load_save_config_submenu(self):
        menu_title = f"{styles.ICON_SAVE} Konfiguracja Globalna"; last_idx = 0
        options: List[MenuOption] = [("1", "Wczytaj konfigurację z pliku (.yaml)", styles.ICON_CONFIG),("2", "Zapisz bieżącą konfigurację do pliku (.yaml)", styles.ICON_SAVE),("0", "Powrót", styles.ICON_EXIT)]
        while True:
            choice, last_idx = self.display.present_interactive_menu(menu_title, options, "Wybierz opcję:", initial_selection_index=last_idx)
            if choice == '0': break
            elif choice == '1': self._load_config_from_file_cli()
            elif choice == '2': self._save_config_to_file_cli()
            else: self.display.display_warning("Nieznana opcja.")
    def _handle_specific_logging_level(self, key: str, display_name: str, parent_last_idx_ref: Optional[List[int]] = None):
        log_level_choices_map_to_int = {"1": logging.DEBUG, "2": logging.INFO, "3": logging.WARNING, "4": logging.ERROR, "5": logging.CRITICAL}
        log_level_display_map_with_desc = { logging.DEBUG: "DEBUG (Szczegółowe)", logging.INFO: "INFO (Standardowe)", logging.WARNING: "WARNING (Ostrzeżenia)", logging.ERROR: "ERROR (Błędy)", logging.CRITICAL: "CRITICAL (Krytyczne)"}
        level_menu_options: List[MenuOption] = []
        for num_key, level_int_val in log_level_choices_map_to_int.items(): display_name_for_option = log_level_display_map_with_desc.get(level_int_val, f"Poziom {level_int_val}"); level_menu_options.append( (num_key, display_name_for_option, None) )
        level_menu_options.append(("q", "Anuluj", styles.ICON_EXIT))
        level_choice_key, selected_choice_idx = self.display.present_interactive_menu(header_text=f"Zmień: {display_name}", menu_options=level_menu_options, prompt_message="Wybierz nowy poziom:", allow_numeric_select=True, initial_selection_index=0 )
        if level_choice_key and level_choice_key in log_level_choices_map_to_int: self._save_and_display_config_update('general', key, log_level_choices_map_to_int[level_choice_key], display_name, True, True)
        elif level_choice_key and level_choice_key.lower() == 'q': self.display.display_info("Zmiana anulowana."); self.display.press_enter_to_continue()
        elif level_choice_key: self.display.display_warning("Nieprawidłowy wybór."); self.display.press_enter_to_continue()
    def _handle_error_handling_setting(self, last_selected_idx_ref: Optional[List[int]] = None): options = {'1': 'stop', '2': 'skip'}; display_map = {'stop': 'Zatrzymaj zadanie', 'skip': 'Pomiń plik'}; self._handle_choice_setting('processing', 'error_handling', "Obsługa błędów transkodowania", options, display_map, last_selected_idx_ref or [0])
    def _handle_output_file_exists_action(self, last_selected_idx_ref: Optional[List[int]] = None): options = {'1': 'overwrite', '2': 'rename', '3': 'skip'}; display_map = {'overwrite': 'Nadpisz', 'rename': 'Zmień nazwę', 'skip': 'Pomiń'}; self._handle_choice_setting('processing', 'output_file_exists', "Konflikt nazw plików wyjściowych", options, display_map, last_selected_idx_ref or [0])
    def _handle_rename_patterns(self): self.display.clear_screen(); self.display.display_header(f"{styles.ICON_SETTINGS} Edycja Wzorców Nazw"); self.display.display_info(f"Placeholdery: {{original_stem}}, {{profile_name}}, {{timestamp}}, {{counter}}"); self._handle_text_input_setting('processing', 'rename_pattern', "Wzorzec dla konfliktu", default_if_empty=DEFAULT_CONFIG['processing']['rename_pattern']); self._handle_text_input_setting('processing', 'repair_rename_pattern', "Wzorzec dla naprawy", default_if_empty=DEFAULT_CONFIG['processing']['repair_rename_pattern'])
    def _handle_supported_extensions(self):
        def extensions_to_str(ext_list: List[str]) -> str: return ", ".join(ext_list) if ext_list else "Wszystkie"
        def validate_extensions_str(ext_str: str) -> Tuple[bool, List[str], Optional[str]]: return self.validator.is_valid_file_extensions_list(ext_str)
        self._handle_text_input_setting('processing', 'supported_file_extensions', "Obsługiwane rozszerzenia (np. .mp4,.mkv)", validation_fn=validate_extensions_str, current_value_transform_fn=extensions_to_str, is_optional=True, default_if_empty=DEFAULT_CONFIG['processing']['supported_file_extensions'])
    def _load_config_from_file_cli(self): 
        self.display.clear_screen(); self.display.display_header(f"{styles.ICON_CONFIG} Wczytaj konfigurację"); fp_str = self.display.get_user_choice("Ścieżka do pliku (.yaml): "); is_v, fp, err = self.validator.is_valid_path(fp_str, True, False)
        if not is_v or not fp: self.display.display_error(f"Błąd: {err or 'Zła ścieżka.'}"); self.display.press_enter_to_continue(); return
        try:
            self.config_manager.load_config(config_file_path_override=fp); self._reload_logging_config(False); # Zmienione na load_config
            if hasattr(self.ffmpeg_manager, 'update_tool_paths_from_config'): self.ffmpeg_manager.update_tool_paths_from_config() # type: ignore
            self.profiler.profiles_file_path = self.config_manager.get_profiles_file_full_path(); self.profiler.profiles = self.profiler._load_profiles()
            if hasattr(self, 'repair_profiler') and self.repair_profiler: self.repair_profiler.profiles_file_path = self.config_manager.get_repair_profiles_file_full_path(); self.repair_profiler.profiles = self.repair_profiler._load_profiles(); logger.info("RepairProfiler przeładował profile naprawy po wczytaniu nowej konfiguracji.")
            self.display.display_success(f"Konfiguracja wczytana z: {fp.resolve()}"); self.display.display_info("Zmiany mogą wymagać restartu dla niektórych ustawień.")
        except Exception as e: self.display.display_error(f"Błąd wczytywania: {e}"); logger.critical(f"Błąd wczytywania config z '{fp.resolve()}': {e}", exc_info=True)
        self.display.press_enter_to_continue()
    def _save_config_to_file_cli(self): 
        self.display.clear_screen(); self.display.display_header(f"{styles.ICON_SAVE} Zapisz konfigurację"); default_save_path = self.config_manager.config_file_path; fp_str = self.display.get_user_choice(f"Ścieżka zapisu (.yaml) [domyślnie: {default_save_path}]: "); target_path: Path = default_save_path
        if fp_str: 
            is_v, rp, err = self.validator.is_valid_path(fp_str, False) 
            # POPRAWKA WCIEŃCIA TUTAJ
            if not is_v or not rp: 
                self.display.display_error(f"Błąd: {err or 'Zła ścieżka.'}")
                self.display.press_enter_to_continue()
                return
            target_path = rp
        
        if not target_path.name.lower().endswith(('.yaml','.yml')):
            if self.display.get_user_choice(f"{styles.STYLE_WARNING}Nazwa pliku nie kończy się na .yaml ani .yml. Kontynuować zapis?{styles.ANSI_RESET} (tak/nie): ").lower() != 'tak':
                self.display.display_info("Zapis anulowany."); self.display.press_enter_to_continue(); return
        try: 
            self.config_manager.save_config(target_path=target_path) 
            self.display.display_success(f"Konfiguracja została pomyślnie zapisana do pliku: {target_path.resolve()}")
        except Exception as e: 
            self.display.display_error(f"Błąd podczas zapisu konfiguracji do pliku: {e}")
            logger.critical(f"Błąd zapisu konfiguracji do '{target_path.resolve()}': {e}", exc_info=True)
        self.display.press_enter_to_continue()

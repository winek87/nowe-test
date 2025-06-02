# src/cli_handlers/damaged_files_cli_handler.py
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable # Dodano Callable
import sys 
import json # Dodano dla logowania debug_config_section

from ..cli_display import CLIDisplay, MenuOption
from ..config_manager import ConfigManager, DEFAULT_CONFIG 
from ..filesystem.damaged_files_manager import DamagedFilesManager
from ..filesystem.path_resolver import PathResolver
from ..filesystem.directory_scanner import DirectoryScanner
from ..ffmpeg.ffmpeg_manager import FFmpegManager
from ..repair_profiler import RepairProfiler 
from ..models import RepairProfile, MediaInfo # Dodano MediaInfo
from .. import cli_styles as styles

try:
    from rich.console import Console
    RICH_FOR_DAMAGED_HANDLER_AVAILABLE = True
except ImportError:
    Console = None # type: ignore
    RICH_FOR_DAMAGED_HANDLER_AVAILABLE = False


logger = logging.getLogger(__name__)

class DamagedFilesCLIHandler:
    def __init__(self,
                 display: CLIDisplay,
                 config_manager: ConfigManager,
                 damaged_files_manager: DamagedFilesManager,
                 ffmpeg_manager: FFmpegManager,
                 path_resolver: PathResolver,
                 directory_scanner: DirectoryScanner,
                 repair_profiler: RepairProfiler
                ):
        logger.debug("DamagedFilesCLIHandler: Inicjalizacja rozpoczęta.")
        self.display = display
        self.config_manager = config_manager
        self.damaged_files_manager = damaged_files_manager
        self.ffmpeg_manager = ffmpeg_manager
        self.path_resolver = path_resolver
        self.directory_scanner = directory_scanner
        self.repair_profiler = repair_profiler
            
        if RICH_FOR_DAMAGED_HANDLER_AVAILABLE and Console is not None:
            self.rich_console = Console()
        else:
            self.rich_console = None
            
        logger.debug("DamagedFilesCLIHandler: Inicjalizacja zakończona.")

    def manage_damaged_files_menu(self):
        # ... (bez zmian od #67)
        last_selected_idx = 0 
        while True:
            menu_title = f"{styles.ICON_BROKEN_FILE} Zarządzanie Uszkodzonymi Plikami"
            menu_options: List[MenuOption] = [("1", "Wyświetl listę uszkodzonych plików", styles.ICON_LIST),("2", "Skanuj folder w poszukiwaniu uszkodzonych plików", styles.ICON_FOLDER_SCAN),("3", "Spróbuj naprawić plik z listy (wg strategii)", styles.ICON_REPAIR),("4", "Weryfikuj pliki na liście (usuń czytelne)", styles.ICON_SUCCESS),("5", "Usuń wybrany plik z listy", styles.ICON_DELETE),("6", "Wyczyść całą listę uszkodzonych plików", styles.ICON_ERROR),("0", "Powrót do menu głównego", styles.ICON_EXIT)]
            choice, last_selected_idx = self.display.present_interactive_menu(header_text=menu_title, menu_options=menu_options,prompt_message="Wybierz opcję:", allow_numeric_select=True,initial_selection_index=last_selected_idx)
            if choice == '1': self.display_damaged_files_list_cli()
            elif choice == '2': self.scan_directory_for_damaged_files_cli()
            elif choice == '3': self.attempt_repair_damaged_file_cli()
            elif choice == '4': self.verify_damaged_files_list_cli()
            elif choice == '5': self._remove_selected_file_from_list_cli()
            elif choice == '6': self._clear_all_damaged_files_confirmed()
            elif choice == '0': logger.debug("Powrót do menu głównego."); break
            else: self.display.display_warning("Nieprawidłowy wybór."); self.display.press_enter_to_continue()

    def _clear_all_damaged_files_confirmed(self):
        # ... (bez zmian od #67)
        self.display.clear_screen(); self.display.display_header(f"{styles.ICON_ERROR} Czyszczenie Listy Uszkodzonych Plików"); self.display.display_warning("UWAGA: Ta operacja nieodwracalnie usunie wszystkie wpisy z listy uszkodzonych plików!")
        confirm_choice = self.display.get_user_choice(f"Czy na pewno chcesz wyczyścić całą listę? ({styles.STYLE_PROMPT}tak{styles.ANSI_RESET}/{styles.STYLE_PROMPT}nie{styles.ANSI_RESET}): ").lower()
        if confirm_choice == 'tak': self.damaged_files_manager.clear_all_damaged_files(); self.display.display_success("Lista uszkodzonych plików została wyczyszczona.")
        else: self.display.display_info("Anulowano czyszczenie listy.")
        self.display.press_enter_to_continue()

    def _remove_selected_file_from_list_cli(self):
        # ... (bez zmian od #67)
        logger.debug("_remove_selected_file_from_list_cli rozpoczęte."); self.display.clear_screen(); self.display.display_header(f"{styles.ICON_DELETE} Usuwanie Pliku z Listy Uszkodzonych")
        damaged_files = self.damaged_files_manager.get_damaged_files()
        if not damaged_files: self.display.display_info("Lista uszkodzonych plików jest pusta."); self.display.press_enter_to_continue(); return
        self.display.display_damaged_files_list(damaged_files)
        choice_str = self.display.get_user_choice(f"Podaj numer pliku z listy do usunięcia (lub '{styles.STYLE_PROMPT}q{styles.ANSI_RESET}' aby anulować): ").lower()
        if choice_str == 'q': self.display.display_info("Usuwanie anulowane."); self.display.press_enter_to_continue(); return
        try:
            choice_idx = int(choice_str) - 1
            if not (0 <= choice_idx < len(damaged_files)): raise ValueError("Nieprawidłowy numer pliku.")
            selected_file_entry = damaged_files[choice_idx]; file_path_val = selected_file_entry.get('file_path')
            if not file_path_val: self.display.display_error("Wybrany wpis nie ma ścieżki."); self.display.press_enter_to_continue(); return
            file_path_to_remove = Path(str(file_path_val))
            confirm_delete = self.display.get_user_choice(f"Na pewno usunąć wpis dla '{styles.STYLE_WARNING}{file_path_to_remove.name}{styles.ANSI_RESET}'? ({styles.STYLE_PROMPT}tak{styles.ANSI_RESET}/{styles.STYLE_PROMPT}nie{styles.ANSI_RESET}): ").lower()
            if confirm_delete == 'tak':
                if self.damaged_files_manager.remove_damaged_file(file_path_to_remove): self.display.display_success(f"Wpis dla '{file_path_to_remove.name}' usunięty.")
                else: self.display.display_error(f"Nie udało się usunąć wpisu dla '{file_path_to_remove.name}'.")
            else: self.display.display_info("Anulowano usuwanie.")
        except ValueError: self.display.display_error("Nieprawidłowy numer.")
        except Exception as e: self.display.display_error(f"Błąd: {e}"); logger.error(f"Błąd w _remove_selected_file_from_list_cli: {e}", exc_info=True)
        self.display.press_enter_to_continue(); logger.debug("_remove_selected_file_from_list_cli zakończone.")

    def scan_directory_for_damaged_files_cli(self):
        # ... (bez zmian od #67)
        logger.debug("scan_directory_for_damaged_files_cli rozpoczęte."); self.display.clear_screen(); self.display.display_header(f"{styles.ICON_FOLDER_SCAN} Skanowanie folderu w poszukiwaniu uszkodzonych plików")
        last_used_dir_path_obj = self.config_manager.get_config_value('paths', 'last_used_source_directory'); last_used_dir_str = str(last_used_dir_path_obj.resolve()) if isinstance(last_used_dir_path_obj, Path) else ""
        prompt_message = "Podaj ścieżkę do katalogu do przeskanowania"; prompt_message += f" (ostatnio: {styles.STYLE_CONFIG_VALUE}{last_used_dir_str}{styles.ANSI_RESET}): " if last_used_dir_str else ": "
        source_dir_path_str = self.display.get_user_choice(prompt_message); final_source_dir_path: Optional[Path] = None
        if not source_dir_path_str and last_used_dir_path_obj and last_used_dir_path_obj.is_dir(): final_source_dir_path = last_used_dir_path_obj; self.display.display_info(f"Używanie ostatnio wybranego katalogu: {final_source_dir_path.resolve()}")
        elif source_dir_path_str:
            path_candidate = Path(source_dir_path_str).expanduser().resolve()
            if path_candidate.is_dir(): final_source_dir_path = path_candidate
            else: self.display.display_error(f"Podana ścieżka nie jest prawidłowym katalogiem: {path_candidate}"); self.display.press_enter_to_continue(); return
        else: self.display.display_error("Nie podano ścieżki do katalogu."); self.display.press_enter_to_continue(); return
        if not final_source_dir_path: self.display.display_error("Nie udało się ustalić katalogu źródłowego."); self.display.press_enter_to_continue(); return
        self.config_manager.set_config_value('paths', 'last_used_source_directory', str(final_source_dir_path))
        recursive_scan = self.config_manager.get_config_value('general', 'recursive_scan', False); supported_extensions = self.config_manager.get_config_value('processing', 'supported_file_extensions', [])
        self.display.display_info(f"Skanuję katalog: {final_source_dir_path} (Rekursywnie: {'Tak' if recursive_scan else 'Nie'})...")
        if hasattr(self.display, 'finalize_progress_display') and self.display._displaying_progress : self.display.finalize_progress_display() # type: ignore
        all_media_infos = self.directory_scanner.scan_directory_for_media_files(source_directory=final_source_dir_path, recursive=recursive_scan, file_extensions=supported_extensions, progress_callback=self.display.display_scan_progress)
        if hasattr(self.display, '_displaying_progress') and self.display._displaying_progress: 
            if hasattr(self.display, 'finalize_progress_display'): self.display.finalize_progress_display() # type: ignore
            else: sys.stdout.write('\r\033[K'); sys.stdout.flush() 
            setattr(self.display, '_displaying_progress', False) 
        if not all_media_infos: self.display.display_success("Skanowanie zakończone. Nie znaleziono żadnych plików pasujących do kryteriów lub katalog jest pusty."); self.display.press_enter_to_continue(); return
        potentially_damaged_files = []
        for media_info in all_media_infos:
            if media_info.error_message or (media_info.duration is None or media_info.duration <= 0):
                media_info.error_message = media_info.error_message or "Plik ma nieprawidłowy lub zerowy czas trwania."
                potentially_damaged_files.append(media_info)
        if not potentially_damaged_files: self.display.display_success(f"Skanowanie zakończone. Przeskanowano {len(all_media_infos)} plików. Nie wykryto potencjalnie uszkodzonych plików.")
        else:
            self.display.display_warning(f"Skanowanie zakończone. Znaleziono {len(potentially_damaged_files)} potencjalnie uszkodzonych plików z {len(all_media_infos)} przeskanowanych:")
            for i, media_info in enumerate(potentially_damaged_files):
                self.display.display_message(f" {i+1}. {styles.ICON_BROKEN_FILE} Plik: {media_info.file_path.name} ({media_info.file_path.parent})")
                self.display.display_error(f"    Problem: {media_info.error_message}")
            add_to_list_choice = self.display.get_user_choice(f"Czy chcesz dodać te {len(potentially_damaged_files)} pliki do globalnej listy uszkodzonych? ({styles.STYLE_PROMPT}tak/nie{styles.ANSI_RESET}): ").lower()
            if add_to_list_choice == 'tak':
                for media_info in potentially_damaged_files: self.damaged_files_manager.add_damaged_file(media_info.file_path, media_info.error_message or "Niesprecyzowany błąd odczytu.", media_info)
                self.display.display_success(f"Dodano/zaktualizowano {len(potentially_damaged_files)} plików na liście uszkodzonych.")
            else: self.display.display_info("Pliki nie zostały dodane do listy uszkodzonych.")
        self.display.press_enter_to_continue(); logger.debug("scan_directory_for_damaged_files_cli zakończone.")


    def _attempt_single_file_repair(self, file_entry: Dict[str, Any], file_index_str: str = "") -> bool:
        original_file_path_val = file_entry.get('file_path')
        if not original_file_path_val:
            self.display.display_error(f"Wpis {file_index_str} nie ma zdefiniowanej ścieżki."); return False
        
        original_file_path = Path(str(original_file_path_val))
        if not original_file_path.exists():
            self.display.display_error(f"Plik źródłowy '{original_file_path.name}' nie istnieje. Pomijanie naprawy."); return False

        self.display.display_message(f"\n--- Naprawa pliku {file_index_str}: '{original_file_path.name}' ({original_file_path.parent}) ---", style=styles.STYLE_PROCESSING_FILE)

        repair_cfg_base_path = 'processing.repair_options'
        attempt_sequentially = self.config_manager.get_config_value(repair_cfg_base_path, 'attempt_sequentially', True)
        use_custom_ffmpeg_profiles_global = self.config_manager.get_config_value(repair_cfg_base_path, 'use_custom_ffmpeg_repair_profiles', True)
        
        # --- Budowanie listy AKTYWNYCH strategii/profili ---
        active_strategies_for_repair: List[Dict[str, Any]] = []

        # 1. Wbudowane strategie (np. mkvmerge_remux)
        default_builtin_strategies_info = DEFAULT_CONFIG.get('processing', {}).get('repair_options', {}).get('builtin_strategies_config', {})
        for builtin_key, builtin_details in default_builtin_strategies_info.items():
            enabled_config_key = f"builtin_strategies_config.{builtin_key}.enabled"
            is_strategy_enabled = self.config_manager.get_config_value(
                repair_cfg_base_path, 
                enabled_config_key, 
                default=builtin_details.get('enabled', False) # Domyślna wartość z DEFAULT_CONFIG
            )
            if is_strategy_enabled:
                active_strategies_for_repair.append({
                    "id": f"builtin_{builtin_key}", 
                    "name": builtin_details.get('name', builtin_key),
                    "type": "builtin",
                    "handler_key": builtin_key # Klucz do obsługi w logice (np. 'mkvmerge_remux')
                })
                logger.debug(f"Strategia wbudowana '{builtin_details.get('name', builtin_key)}' jest AKTYWNA.")
            else:
                logger.debug(f"Strategia wbudowana '{builtin_details.get('name', builtin_key)}' jest WYŁĄCZONA.")

        # 2. Niestandardowe Profile Naprawy FFmpeg
        if use_custom_ffmpeg_profiles_global:
            enabled_ffmpeg_profile_ids = self.config_manager.get_config_value(repair_cfg_base_path, 'enabled_ffmpeg_profile_ids', [])
            all_custom_profiles = self.repair_profiler.get_all_profiles()
            for profile in all_custom_profiles:
                if str(profile.id) in enabled_ffmpeg_profile_ids:
                    active_strategies_for_repair.append({
                        "id": str(profile.id), 
                        "name": profile.name,
                        "type": "ffmpeg_profile",
                        "profile_object": profile 
                    })
                    logger.debug(f"Profil FFmpeg '{profile.name}' (ID: {profile.id}) jest AKTYWNY.")
                else:
                    logger.debug(f"Profil FFmpeg '{profile.name}' (ID: {profile.id}) jest WYŁĄCZONY (brak na liście enabled_ffmpeg_profile_ids).")
        else:
            logger.info("Używanie niestandardowych profili FFmpeg jest globalnie WYŁĄCZONE.")


        if not active_strategies_for_repair:
            self.display.display_warning("Brak aktywnych strategii naprawy skonfigurowanych do użycia. Nie można kontynuować naprawy."); return False

        # TODO: Implementacja sortowania strategii, jeśli potrzebna (np. domyślny FFmpeg_copy jako pierwszy)

        strategies_to_attempt_execution: List[Dict[str, Any]] = []
        if attempt_sequentially:
            strategies_to_attempt_execution = active_strategies_for_repair
            self.display.display_info(f"Automatyczna próba naprawy sekwencyjnej (liczba aktywnych strategii/profili: {len(strategies_to_attempt_execution)}).")
        else: # Wybór przez użytkownika
            if len(active_strategies_for_repair) == 1:
                strategies_to_attempt_execution = [active_strategies_for_repair[0]]
                self.display.display_info(f"Użycie jedynej aktywnej strategii: {styles.STYLE_PROMPT}{strategies_to_attempt_execution[0]['name']}{styles.ANSI_RESET}")
            elif len(active_strategies_for_repair) > 1:
                menu_opts_repair: List[MenuOption] = [(s['id'], s['name'], styles.ICON_REPAIR) for s in active_strategies_for_repair]
                menu_opts_repair.append( ("cancel_repair", "Anuluj naprawę tego pliku", styles.ICON_EXIT) )
                self.display.clear_screen()
                chosen_strategy_id, _ = self.display.present_interactive_menu(
                    header_text=f"Wybierz strategię naprawy dla '{original_file_path.name}'",
                    menu_options=menu_opts_repair, prompt_message="Wybierz strategię:", initial_selection_index=0
                )
                if chosen_strategy_id == "cancel_repair" or not chosen_strategy_id:
                    self.display.display_info("Naprawa anulowana."); return False
                selected_strategy_details = next((s for s in active_strategies_for_repair if s['id'] == chosen_strategy_id), None)
                if selected_strategy_details: strategies_to_attempt_execution = [selected_strategy_details]
                else: self.display.display_error("Błąd: nie znaleziono wybranej strategii."); return False
            else: # Nie powinno się zdarzyć, bo sprawdzaliśmy active_strategies_for_repair na początku
                self.display.display_warning("Brak aktywnych strategii do wyboru."); return False

        overall_repair_success = False
        final_repaired_file_path_for_job: Optional[Path] = None

        for strategy_details in strategies_to_attempt_execution:
            strategy_id = strategy_details['id']; strategy_name = strategy_details['name']
            strategy_type = strategy_details['type']
            
            self.display.display_message(f"\n{styles.STYLE_INFO}Próba strategii:{styles.ANSI_RESET} {styles.STYLE_PROMPT}{strategy_name}{styles.ANSI_RESET}", style=styles.STYLE_HEADER)
            repair_output_dir = Path(str(self.config_manager.get_config_value('paths', 'default_repaired_directory'))).expanduser().resolve()
            
            attempt_suffix = strategy_id.replace("builtin_", "").replace("-","_").replace(" ","_")[:15] 
            temp_repaired_file_name = f"{original_file_path.stem}_repair_attempt_{attempt_suffix}{original_file_path.suffix}"
            current_attempt_output_path = self.path_resolver.generate_unique_output_path(repair_output_dir / temp_repaired_file_name, is_repair_path=False)
            
            self.display.display_info(f"Docelowa ścieżka dla tej próby: {current_attempt_output_path}")

            success_this_strategy = False; error_msg_this_strategy: Optional[str] = None

            if strategy_type == "ffmpeg_profile":
                profile_object: Optional[RepairProfile] = strategy_details.get("profile_object")
                if profile_object:
                    if profile_object.applies_to_mkv_only and original_file_path.suffix.lower() != ".mkv":
                        self.display.display_warning(f"Profil FFmpeg '{profile_object.name}' jest tylko dla .mkv. Pomijanie dla '{original_file_path.name}'.")
                        error_msg_this_strategy = "Nieodpowiedni typ pliku dla tego profilu FFmpeg."; success_this_strategy = False
                    else:
                        success_this_strategy, error_msg_this_strategy = self.ffmpeg_manager.execute_ffmpeg_repair_with_profile(
                            original_file_path, current_attempt_output_path, profile_object
                        )
                else: 
                    error_msg_this_strategy = f"Brak obiektu profilu dla strategii FFmpeg (ID: {strategy_id})."; logger.error(error_msg_this_strategy)
            elif strategy_id == "builtin_mkvmerge_remux": # Lub strategy_details.get("handler_key") == "mkvmerge_remux"
                if original_file_path.suffix.lower() == ".mkv":
                    success_this_strategy, error_msg_this_strategy = self.ffmpeg_manager.remux_file_with_mkvmerge(original_file_path, current_attempt_output_path)
                else:
                    self.display.display_warning(f"Strategia '{strategy_name}' tylko dla .mkv. Pomijanie dla '{original_file_path.name}'.")
                    error_msg_this_strategy = "Nieodpowiedni typ pliku."; success_this_strategy = False
                    if attempt_sequentially: self.display.display_separator(length=30); continue # Przejdź do następnej strategii
                    else: break # Jeśli nie sekwencyjnie, a ta strategia nie pasuje, zakończ
            # Można dodać obsługę innych "handler_key" dla wbudowanych strategii
            
            if success_this_strategy:
                self.display.display_success(f"Strategia '{strategy_name}' pomyślna. Plik tymczasowy: {current_attempt_output_path.name}")
                final_repaired_file_path_for_job = current_attempt_output_path
                if self.config_manager.get_config_value('processing', 'verify_repaired_files', True):
                    self.display.display_info(f"Weryfikacja pliku '{final_repaired_file_path_for_job.name}'...")
                    if self.ffmpeg_manager.is_file_readable_by_ffprobe(final_repaired_file_path_for_job):
                        self.display.display_success("Naprawiony plik zweryfikowany (czytelny).")
                        self.damaged_files_manager.update_damaged_file_status(original_file_path, f"Naprawiono ({strategy_name})", None)
                        self.damaged_files_manager.remove_damaged_file(original_file_path)
                        overall_repair_success = True; break 
                    else:
                        self.display.display_warning(f"Naprawiony plik '{final_repaired_file_path_for_job.name}' nieczytelny po weryfikacji.")
                        self.damaged_files_manager.update_damaged_file_status(original_file_path, f"NaprawaWeryfikacjaFail({strategy_name})", f"Naprawiony plik ({final_repaired_file_path_for_job.name}) nieczytelny.")
                        if final_repaired_file_path_for_job.exists():
                            try: final_repaired_file_path_for_job.unlink(missing_ok=True)
                            except OSError as e_del: logger.warning(f"Nie można usunąć pliku '{final_repaired_file_path_for_job.name}' po nieudanej weryfikacji: {e_del}")
                        final_repaired_file_path_for_job = None
                else: # Weryfikacja wyłączona
                    self.display.display_info("Pominięto weryfikację naprawionego pliku.")
                    self.damaged_files_manager.update_damaged_file_status(original_file_path, f"NaprawionoBezWeryfikacji ({strategy_name})", None)
                    self.damaged_files_manager.remove_damaged_file(original_file_path)
                    overall_repair_success = True; break
            else: # Strategia nie powiodła się
                self.display.display_error(f"Strategia '{strategy_name}' nie powiodła się.");
                if error_msg_this_strategy: self.display.display_error(f"  Szczegóły: {error_msg_this_strategy}")
                if current_attempt_output_path.exists():
                    try:
                        if current_attempt_output_path.stat().st_size == 0: 
                            current_attempt_output_path.unlink(missing_ok=True)
                            logger.info(f"Usunięto pusty plik po nieudanej strategii: {current_attempt_output_path}")
                    except OSError as e: logger.warning(f"Nie można usunąć pliku po nieudanej strategii '{strategy_name}': {e}")
            
            if not attempt_sequentially and not overall_repair_success: break # Jeśli nie sekwencyjnie i pierwsza próba nieudana, zakończ
            if attempt_sequentially: self.display.display_separator(length=30) # Separator między próbami sekwencyjnymi

        if overall_repair_success:
            self.display.display_success(f"Plik '{original_file_path.name}' został pomyślnie naprawiony.")
            if final_repaired_file_path_for_job: self.display.display_info(f"Naprawiona wersja zapisana jako: {final_repaired_file_path_for_job}")
        else:
            self.display.display_error(f"Wszystkie aktywne strategie naprawy dla '{original_file_path.name}' nie powiodły się.")
            self.damaged_files_manager.update_damaged_file_status(original_file_path, "NaprawaNieudanaFull", "Żadna aktywna strategia nie zadziałała.")
        return overall_repair_success

    def attempt_repair_damaged_file_cli(self):
        # ... (bez zmian od #67)
        logger.debug("attempt_repair_damaged_file_cli rozpoczęte."); self.display.clear_screen(); self.display.display_header(f"{styles.ICON_REPAIR} Próba naprawy uszkodzonych plików")
        damaged_files = self.damaged_files_manager.get_damaged_files()
        if not damaged_files: self.display.display_info("Lista uszkodzonych plików jest pusta."); self.display.press_enter_to_continue(); return
        last_selected_idx = 0
        while True:
            self.display.clear_screen(); self.display.display_header(f"{styles.ICON_REPAIR} Wybierz plik do naprawy")
            menu_options_files: List[MenuOption] = []
            for i, entry in enumerate(damaged_files):
                fp_val = entry.get('file_path','N/A'); file_name_disp = Path(str(fp_val)).name if fp_val != 'N/A' else 'Brak ścieżki'; status_disp = entry.get('status', 'Nieznany')
                menu_options_files.append( (str(i+1), f"{file_name_disp} (Status: {status_disp})", styles.ICON_BROKEN_FILE) )
            menu_options_files.append( ("all", "Napraw wszystkie z listy", styles.ICON_REPAIR) ); menu_options_files.append( ("q", "Anuluj i wróć", styles.ICON_EXIT) )
            choice_str, last_selected_idx = self.display.present_interactive_menu(header_text="Wybierz plik lub opcję", menu_options=menu_options_files,prompt_message="Wybierz numer pliku, 'all' lub 'q':",initial_selection_index=last_selected_idx, allow_numeric_select=True)
            if choice_str.lower() == 'q': self.display.display_info("Naprawa anulowana."); break
            if choice_str.lower() == 'all':
                self.display.display_info(f"Rozpoczynanie próby naprawy wszystkich {len(damaged_files)} plików z listy...")
                successful_repairs = 0; failed_repairs = 0
                for i, file_entry in enumerate(list(damaged_files)): 
                    if self._attempt_single_file_repair(file_entry, file_index_str=f"({i+1}/{len(damaged_files)})"): successful_repairs += 1
                    else: failed_repairs += 1
                    if i < len(damaged_files) -1: self.display.display_separator(length=50)
                self.display.display_message("\n--- Podsumowanie naprawy wszystkich plików ---", style=styles.STYLE_HEADER); self.display.display_success(f"Pomyślnie przetworzono/naprawiono: {successful_repairs} plików."); self.display.display_error(f"Nie udało się naprawić: {failed_repairs} plików."); self.display.press_enter_to_continue(); break 
            else:
                try:
                    choice_idx = int(choice_str) - 1
                    if not (0 <= choice_idx < len(damaged_files)): raise ValueError("Nieprawidłowy numer pliku.")
                    selected_file_entry = damaged_files[choice_idx]
                    self._attempt_single_file_repair(selected_file_entry, file_index_str=str(choice_idx + 1))
                    damaged_files = self.damaged_files_manager.get_damaged_files() 
                    if not damaged_files: self.display.display_info("Lista uszkodzonych plików jest teraz pusta."); self.display.press_enter_to_continue(); break
                    self.display.press_enter_to_continue("Naciśnij Enter, aby kontynuować zarządzanie listą...")
                except ValueError: self.display.display_error("Nieprawidłowy numer pliku lub wybór."); self.display.press_enter_to_continue()
                except Exception as e: self.display.display_error(f"Wystąpił nieoczekiwany błąd: {e}"); logger.critical(f"Nieoczekiwany błąd w attempt_repair_damaged_file_cli (pojedynczy plik): {e}", exc_info=True); self.display.press_enter_to_continue()
        logger.debug("attempt_repair_damaged_file_cli zakończone.")

    def display_damaged_files_list_cli(self):
        # ... (bez zmian od #67)
        logger.debug("display_damaged_files_list_cli rozpoczęte."); damaged_files = self.damaged_files_manager.get_damaged_files(); self.display.display_damaged_files_list(damaged_files); logger.debug("display_damaged_files_list_cli zakończone.")

    def verify_damaged_files_list_cli(self):
        # ... (bez zmian od #67)
        logger.debug("verify_damaged_files_list_cli rozpoczęte."); self.display.clear_screen(); self.display.display_header(f"{styles.ICON_LIST} Weryfikacja Listy Uszkodzonych Plików"); self.display.display_info("Trwa weryfikacja plików z listy. Może to chwilę potrwać...")
        damaged_files_before = self.damaged_files_manager.get_damaged_files(); total_to_verify = len(damaged_files_before)
        progress_callback_fn: Optional[Callable[[int, int, str], None]] = None
        if total_to_verify > 0:
            def verification_progress_callback(current: int, total: int, filename: str): self.display.display_message(f"\rWeryfikacja: {current}/{total} - {filename}...", new_line=False, style=styles.STYLE_INFO); sys.stdout.write("\033[K"); sys.stdout.flush()
            progress_callback_fn = verification_progress_callback
        updated_list = self.damaged_files_manager.verify_files_on_list(progress_callback=progress_callback_fn) # type: ignore
        if total_to_verify > 0 : 
            if progress_callback_fn or (hasattr(self.display, '_displaying_progress') and self.display._displaying_progress): sys.stdout.write("\r\033[K\n"); sys.stdout.flush(); 
            if hasattr(self.display, '_displaying_progress'): setattr(self.display, '_displaying_progress', False) # type: ignore
        self.display.display_success("Weryfikacja zakończona.")
        files_removed_count = total_to_verify - len(updated_list)
        if files_removed_count > 0: self.display.display_info(f"Usunięto {files_removed_count} czytelnych plików z listy.")
        if not updated_list: self.display.display_info("Lista uszkodzonych plików jest teraz pusta.")
        else: self.display.display_info(f"Pozostało {len(updated_list)} plików na liście uszkodzonych."); self.display.display_damaged_files_list(updated_list); return 
        self.display.press_enter_to_continue(); logger.debug("verify_damaged_files_list_cli zakończone.")

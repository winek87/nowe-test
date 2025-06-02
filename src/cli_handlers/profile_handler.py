# src/cli_handlers/profile_handler.py
import logging
import uuid
from typing import Optional, List, Dict, Any, Tuple
import re
import json

from ..cli_display import CLIDisplay, MenuOption, READCHAR_AVAILABLE as DISPLAY_READCHAR_AVAILABLE
from ..config_manager import ConfigManager
from ..models import EncodingProfile
from ..profiler import Profiler
from ..validation.input_validator import InputValidator
from .. import cli_styles as styles

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.padding import Padding
    RICH_FOR_PROFILE_HANDLER_AVAILABLE = True
except ImportError:
    Console, Panel, Text, Table, Padding = None, None, None, None, None # type: ignore
    RICH_FOR_PROFILE_HANDLER_AVAILABLE = False

logger = logging.getLogger(__name__)

class ProfileCLIHandler:
    def __init__(self,
                 display: CLIDisplay,
                 config_manager: ConfigManager,
                 profiler: Profiler):
        logger.debug("ProfileCLIHandler: Inicjalizacja rozpoczęta.")
        self.display = display
        self.config_manager = config_manager
        self.profiler = profiler
        self.validator = InputValidator()
        
        if RICH_FOR_PROFILE_HANDLER_AVAILABLE and Console is not None:
            self.rich_console = Console()
        else:
            self.rich_console = None
            
        logger.debug("ProfileCLIHandler: Inicjalizacja zakończona.")

    def manage_profiles_menu(self):
        """Główne menu zarządzania profilami, teraz z nawigacją strzałkami."""
        menu_title = f"{styles.ICON_PROFILE} Zarządzanie Profilami Kodowania"
        
        menu_options: List[MenuOption] = [
            ("1", "Wyświetl listę profili", styles.ICON_LIST),
            ("2", "Dodaj nowy profil", styles.ICON_PLAY),
            ("3", "Edytuj istniejący profil", styles.ICON_SETTINGS),
            ("4", "Usuń profil", styles.ICON_DELETE if hasattr(styles, 'ICON_DELETE') else "🗑️"),
            ("5", "Ustaw aktywny profil", styles.ICON_SUCCESS),
            ("0", "Powrót do menu głównego", styles.ICON_EXIT)
        ]

        while True:
            # Metoda present_interactive_menu sama czyści ekran i wyświetla nagłówek
            if hasattr(self.display, 'present_interactive_menu') and DISPLAY_READCHAR_AVAILABLE:
                choice = self.display.present_interactive_menu(
                    header_text=menu_title,
                    menu_options=menu_options,
                    prompt_message="Wybierz opcję:",
                    allow_numeric_select=True
                )
            else: # Fallback, jeśli menu interaktywne niedostępne
                self.display.clear_screen()
                self.display.display_header(menu_title)
                for key, text, icon in menu_options:
                    # Upewnij się, że ikona jest stringiem, jeśli styl jej nie definiuje
                    icon_display = icon if icon else ""
                    self.display.display_info(f"  {icon_display} {key}. {text}")
                self.display.display_separator()
                choice = self.display.get_user_choice("Wybierz opcję: ")

            if choice == '1':
                self._list_profiles()
            elif choice == '2':
                self._add_new_profile()
            elif choice == '3':
                self._edit_profile()
            elif choice == '4':
                self._delete_profile()
            elif choice == '5':
                self._set_active_profile()
            elif choice == '0':
                logger.debug("Powrót do menu głównego z zarządzania profilami.")
                break
            else:
                self.display.display_warning("Nieprawidłowy wybór.")
                self.display.press_enter_to_continue()

    def _list_profiles(self, show_details: bool = False, for_selection: bool = False) -> Optional[List[EncodingProfile]]:
        # (bez zmian od ostatniej wersji)
        if not for_selection:
            self.display.clear_screen()
            if not (self.rich_console and Table and Panel and Text and show_details):
                 self.display.display_header(f"{styles.ICON_LIST} Lista Profili Kodowania")

        profiles = self.profiler.get_all_profiles()
        active_profile = self.profiler.get_active_profile()

        if not profiles:
            if not for_selection:
                self.display.display_info("Brak zdefiniowanych profili.")
        elif self.rich_console and Table and Panel and Text and not for_selection and show_details:
            table = Table(title=f"{styles.ICON_LIST} Szczegóły Profili Kodowania", border_style="blue", show_lines=True, expand=False)
            table.add_column("Lp.", style="dim", width=3, justify="right")
            table.add_column("Nazwa", style="cyan", min_width=20)
            table.add_column("Aktywny", justify="center", width=8)
            table.add_column("Opis", style="white", overflow="fold", min_width=30, ratio=2)
            table.add_column("Rozsz.", style="magenta", width=7)
            table.add_column("Parametry FFmpeg", style="yellow", overflow="fold", min_width=30, ratio=3)
            table.add_column("Ust. Wyj.", style="dim", overflow="fold", min_width=15, ratio=1)

            for i, profile in enumerate(profiles):
                active_marker_text = Text("TAK", style="bold green") if active_profile and active_profile.id == profile.id else Text("NIE", style="dim")
                params_str = ' '.join(profile.ffmpeg_params)
                settings_str = json.dumps(profile.output_settings, ensure_ascii=False, indent=2) if profile.output_settings else "-"
                
                table.add_row(
                    str(i + 1),
                    profile.name,
                    active_marker_text,
                    profile.description if profile.description else "-",
                    f".{profile.output_extension}",
                    params_str,
                    settings_str
                )
            self.rich_console.print(table)
        else: 
            for i, profile in enumerate(profiles):
                active_marker = f" ({styles.STYLE_SUCCESS}AKTYWNY{styles.ANSI_RESET})" if active_profile and active_profile.id == profile.id else ""
                self.display.display_info(f"{i + 1}. {profile.name}{active_marker}")
                if not for_selection:
                    self.display.display_message(f"   Opis: {profile.description if profile.description else 'Brak'}", style=styles.STYLE_INFO)
                    if show_details:
                        self.display.display_message(f"   ID: {profile.id}", style=styles.STYLE_INFO)
                        self.display.display_message(f"   Rozszerzenie wyjściowe: .{profile.output_extension}", style=styles.STYLE_INFO)
                        self.display.display_message(f"   Parametry FFmpeg: {' '.join(profile.ffmpeg_params)}", style=styles.STYLE_INFO)
                        if profile.output_settings:
                            self.display.display_message(f"   Ustawienia wyjściowe: {json.dumps(profile.output_settings, ensure_ascii=False, indent=2)}", style=styles.STYLE_INFO)
                        if i < len(profiles) - 1 : self.display.display_separator(length=40)
        
        if for_selection:
            return profiles

        if not show_details and profiles:
             details_choice = self.display.get_user_choice(f"Wyświetlić szczegóły wszystkich profili? ({styles.STYLE_PROMPT}tak/nie{styles.ANSI_RESET}): ").lower()
             if details_choice == 'tak':
                  self._list_profiles(show_details=True)
                  return None
        self.display.press_enter_to_continue()
        return None

    def _get_profile_data_from_user(self, existing_profile: Optional[EncodingProfile] = None) -> Optional[EncodingProfile]:
        # (bez zmian)
        if existing_profile:
            self.display.display_info(f"Edytujesz profil: {existing_profile.name}")
            name = self.display.get_user_choice(f"Nowa nazwa (zostaw puste, aby zachować '{existing_profile.name}'): ") or existing_profile.name
            description = self.display.get_user_choice(f"Nowy opis (zostaw puste, aby zachować '{existing_profile.description}'): ") or existing_profile.description
            ffmpeg_params_str = self.display.get_user_choice(f"Nowe parametry FFmpeg (oddzielone spacją, zostaw puste, aby zachować '{' '.join(existing_profile.ffmpeg_params)}'): ")
            ffmpeg_params = ffmpeg_params_str.split() if ffmpeg_params_str else existing_profile.ffmpeg_params
            output_extension = self.display.get_user_choice(f"Nowe rozszerzenie wyjściowe (np. mp4, mkv; zostaw puste, aby zachować '{existing_profile.output_extension}'): ").lstrip('.') or existing_profile.output_extension
            profile_subdir_current = existing_profile.output_settings.get('subdirectory', '')
            profile_subdir = self.display.get_user_choice(f"Podkatalog wyjściowy (opcjonalnie, zostaw puste, aby zachować '{profile_subdir_current}'): ") or profile_subdir_current
            output_settings = {'subdirectory': profile_subdir.strip()} if profile_subdir.strip() else existing_profile.output_settings
            profile_id = existing_profile.id
        else:
            self.display.display_info("Tworzenie nowego profilu.")
            name = self.display.get_user_choice("Nazwa profilu: ")
            if not name: self.display.display_warning("Nazwa profilu nie może być pusta."); return None
            description = self.display.get_user_choice("Opis profilu (opcjonalnie): ")
            ffmpeg_params_str = self.display.get_user_choice("Parametry FFmpeg (oddzielone spacją, np. -c:v libx264 -crf 23): ")
            if not ffmpeg_params_str: self.display.display_warning("Parametry FFmpeg nie mogą być puste."); return None
            ffmpeg_params = ffmpeg_params_str.split()
            output_extension = self.display.get_user_choice("Rozszerzenie pliku wyjściowego (np. mp4, mkv): ").lstrip('.')
            if not output_extension: self.display.display_warning("Rozszerzenie wyjściowe nie może być puste."); return None
            profile_subdir = self.display.get_user_choice("Podkatalog wyjściowy (opcjonalnie, np. h265_files): ")
            output_settings = {'subdirectory': profile_subdir.strip()} if profile_subdir.strip() else {}
            profile_id = uuid.uuid4()
        if not name.strip(): self.display.display_error("Nazwa profilu nie może być pusta."); return None
        if not ffmpeg_params: self.display.display_error("Parametry FFmpeg nie mogą być puste."); return None
        if not output_extension.strip(): self.display.display_error("Rozszerzenie wyjściowe nie może być puste."); return None
        return EncodingProfile(id=profile_id, name=name.strip(), description=description.strip(), ffmpeg_params=ffmpeg_params, output_extension=output_extension.strip(), output_settings=output_settings)

    def _add_new_profile(self): # (bez zmian)
        self.display.clear_screen(); self.display.display_header("Dodawanie Nowego Profilu")
        profile_data = self._get_profile_data_from_user()
        if profile_data:
            try: self.profiler.add_profile(profile_data); self.display.display_success(f"Profil '{profile_data.name}' został pomyślnie dodany.")
            except ValueError as e: self.display.display_error(f"Błąd dodawania profilu: {e}")
            except Exception as e: self.display.display_error(f"Nieoczekiwany błąd podczas dodawania profilu: {e}"); logger.error("Nieoczekiwany błąd w _add_new_profile", exc_info=True)
        else: self.display.display_warning("Anulowano dodawanie profilu lub podano nieprawidłowe dane.")
        self.display.press_enter_to_continue()

    def _select_profile_for_action(self, action_name: str) -> Optional[EncodingProfile]: # (bez zmian)
        profiles = self._list_profiles(for_selection=True) 
        if not profiles: self.display.display_info("Brak zdefiniowanych profili."); return None
        menu_title = f"Wybierz profil do {action_name}"
        menu_options: List[MenuOption] = []
        for i, profile in enumerate(profiles): menu_options.append((str(profile.id), profile.name, styles.ICON_PROFILE)) 
        menu_options.append(("q", "Anuluj", styles.ICON_EXIT))
        if hasattr(self.display, 'present_interactive_menu') and DISPLAY_READCHAR_AVAILABLE:
            self.display.clear_screen()
            choice_id_str = self.display.present_interactive_menu(header_text=menu_title, menu_options=menu_options, prompt_message=f"Wybierz profil strzałkami (↑↓), Enter, lub 'q' aby anulować:", allow_numeric_select=False)
            if choice_id_str is None or choice_id_str.lower() == 'q': return None
            return self.profiler.get_profile_by_id(choice_id_str)
        else: 
            self.display.clear_screen(); self.display.display_header(menu_title)
            for i, profile in enumerate(profiles): self.display.display_info(f" {i + 1}. {profile.name}")
            self.display.display_separator(); choice_str = self.display.get_user_choice(f"Podaj numer profilu (lub '{styles.STYLE_PROMPT}q{styles.ANSI_RESET}' aby anulować): ")
            if choice_str.lower() == 'q': return None
            try:
                profile_idx = int(choice_str) - 1
                if 0 <= profile_idx < len(profiles): return profiles[profile_idx]
                else: self.display.display_warning("Nieprawidłowy numer profilu.")
            except ValueError: self.display.display_warning("Wprowadź numer.")
        return None

    def _edit_profile(self): # (bez zmian)
        self.display.clear_screen(); self.display.display_header("Edycja Profilu Kodowania")
        profile_to_edit = self._select_profile_for_action("edycji")
        if not profile_to_edit: self.display.press_enter_to_continue(); return
        updated_profile_data = self._get_profile_data_from_user(existing_profile=profile_to_edit)
        if updated_profile_data:
            try:
                if self.profiler.update_profile(updated_profile_data): self.display.display_success(f"Profil '{updated_profile_data.name}' został pomyślnie zaktualizowany.")
                else: self.display.display_error(f"Nie znaleziono profilu o ID {updated_profile_data.id} do aktualizacji.")
            except ValueError as e: self.display.display_error(f"Błąd aktualizacji profilu: {e}")
            except Exception as e: self.display.display_error(f"Nieoczekiwany błąd podczas aktualizacji profilu: {e}"); logger.error("Nieoczekiwany błąd w _edit_profile", exc_info=True)
        else: self.display.display_warning("Anulowano edycję profilu lub podano nieprawidłowe dane.")
        self.display.press_enter_to_continue()

    def _delete_profile(self): # (bez zmian)
        self.display.clear_screen(); self.display.display_header("Usuwanie Profilu Kodowania")
        profile_to_delete = self._select_profile_for_action("usunięcia")
        if not profile_to_delete: self.display.press_enter_to_continue(); return
        confirm = self.display.get_user_choice(f"Czy na pewno chcesz usunąć profil '{profile_to_delete.name}'? ({styles.STYLE_PROMPT}tak/nie{styles.ANSI_RESET}): ").lower()
        if confirm == 'tak':
            if self.profiler.delete_profile(str(profile_to_delete.id)): self.display.display_success(f"Profil '{profile_to_delete.name}' został usunięty.")
            else: self.display.display_error(f"Nie udało się usunąć profilu '{profile_to_delete.name}' (nie znaleziono).")
        else: self.display.display_info("Usuwanie profilu anulowane.")
        self.display.press_enter_to_continue()

    def _set_active_profile(self): # (bez zmian)
        self.display.clear_screen(); self.display.display_header("Ustawianie Aktywnego Profilu")
        profile_to_set_active = self._select_profile_for_action("ustawienia jako aktywny")
        if not profile_to_set_active: self.display.press_enter_to_continue(); return
        self.profiler.set_active_profile_id(profile_to_set_active.id)
        self.display.display_success(f"Profil '{profile_to_set_active.name}' został ustawiony jako aktywny.")
        self.display.press_enter_to_continue()

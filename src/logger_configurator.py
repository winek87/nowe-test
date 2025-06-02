# src/logger_configurator.py
import logging
import sys
from pathlib import Path
from typing import Union, Optional
from datetime import datetime

try:
    from rich.logging import RichHandler
    from rich.console import Console as RichConsole 
    RICH_LOGGING_AVAILABLE = True
except ImportError:
    RICH_LOGGING_AVAILABLE = False
    RichHandler = None # type: ignore
    RichConsole = None # type: ignore

class LoggerConfigurator:
    """
    Konfiguruje system logowania aplikacji.
    """
    @staticmethod
    def setup_logging(log_file: Optional[Union[str, Path]] = None,
                      log_level_file: int = logging.INFO,
                      log_level_console: int = logging.INFO,
                      console_logging_enabled: bool = True, 
                      clear_log_on_start: bool = True,
                      log_format: str = '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
                      date_format: str = '%Y-%m-%d %H:%M:%S'):
        """
        Ustawia konfigurację logowania dla aplikacji.
        """
        root_logger = logging.getLogger()
        
        # Usuń wszystkie istniejące handlery z root loggera przed dodaniem nowych
        # To zapobiega duplikacji logów przy wielokrotnym wywołaniu setup_logging
        for handler in root_logger.handlers[:]:
            handler.close() # Zamknij handler przed usunięciem
            root_logger.removeHandler(handler)

        # Ustal efektywny poziom dla root loggera
        # Powinien być to najniższy poziom z aktywnych handlerów
        # lub WARNING, jeśli żadne logowanie nie jest aktywne.
        if console_logging_enabled and log_file:
            effective_root_level = min(log_level_file, log_level_console)
        elif console_logging_enabled:
            effective_root_level = log_level_console
        elif log_file:
            effective_root_level = log_level_file
        else: # Żadne logowanie nie jest włączone
            effective_root_level = logging.WARNING # Lub logging.CRITICAL, aby nic nie szło domyślnie
            # Można też po prostu nie ustawiać poziomu roota, jeśli nie ma handlerów,
            # ale ustawienie na wysoki poziom jest bezpieczniejsze.
            # Lub root_logger.disabled = True, jeśli nie ma handlerów.

        root_logger.setLevel(effective_root_level)
        # logging.debug(f"Poziom root loggera ustawiony na: {logging.getLevelName(root_logger.level)}")


        formatter = logging.Formatter(log_format, date_format)
        
        # --- Console Handler ---
        if console_logging_enabled:
            console_handler_instance: Optional[logging.Handler] = None
            if RICH_LOGGING_AVAILABLE and RichHandler is not None and RichConsole is not None:
                # Użyj RichHandler dla lepszego formatowania
                console_handler_instance = RichHandler(
                    level=log_level_console, # Poziom dla tego handlera
                    console=RichConsole(stderr=True), # Logi do stderr
                    show_time=True, # RichHandler ma swój własny format czasu
                    show_level=True,
                    show_path=False, 
                    markup=True,      
                    rich_tracebacks=True,
                    log_time_format="[%X]" # Prostszy format czasu dla RichHandlera
                )
                # RichHandler ma swoje własne formatowanie, które jest zazwyczaj bardziej rozbudowane.
                # Jeśli chcemy użyć naszego `formatter`, musielibyśmy użyć standardowego `StreamHandler`.
                # Zdecydujmy, czy chcemy spójności formatu, czy lepszego wyglądu z Rich.
                # Na razie zostawiamy domyślne (rozbudowane) formatowanie RichHandlera.
            else: # Fallback do standardowego StreamHandler
                console_handler_instance = logging.StreamHandler(sys.stderr) 
                console_handler_instance.setFormatter(formatter) # Użyj naszego standardowego formattera
                console_handler_instance.setLevel(log_level_console) # Poziom dla tego handlera
            
            if console_handler_instance:
                root_logger.addHandler(console_handler_instance)
                # logging.debug(f"Dodano handler konsoli z poziomem: {logging.getLevelName(log_level_console)}")

        # --- File Handler ---
        log_file_path_resolved: Optional[Path] = None
        file_handler_added = False
        if log_file:
            try:
                log_file_path_resolved = Path(log_file).resolve()
                log_file_path_resolved.parent.mkdir(parents=True, exist_ok=True)
                
                file_open_mode = 'w' if clear_log_on_start else 'a'
                
                file_handler = logging.FileHandler(log_file_path_resolved, mode=file_open_mode, encoding='utf-8')
                file_handler.setFormatter(formatter)
                file_handler.setLevel(log_level_file) # Poziom dla tego handlera
                root_logger.addHandler(file_handler)
                file_handler_added = True
                
                if clear_log_on_start and file_open_mode == 'w':
                    # Logowanie informacji o wyczyszczeniu pliku powinno nastąpić PO dodaniu handlera,
                    # aby ta informacja trafiła do nowego (czystego) pliku.
                    root_logger.info(f"Plik logu '{log_file_path_resolved}' został wyczyszczony/utworzony przy starcie aplikacji.")
                
            except Exception as e:
                # Zapisz błąd konfiguracji logowania do pliku na stderr, jeśli konsola jest wyłączona
                # lub jeśli handler konsolowy jeszcze nie istnieje.
                sys.stderr.write(f"KRYTYCZNY BŁĄD konfiguracji logowania do pliku {log_file_path_resolved or log_file}: {e}\n")
                # Można też użyć print()
                # print(f"KRYTYCZNY BŁĄD konfiguracji logowania do pliku {log_file_path_resolved or log_file}: {e}", file=sys.stderr)

        # Logowanie informacji o stanie loggerów (teraz, gdy wszystkie handlery są potencjalnie dodane)
        if file_handler_added and log_file_path_resolved:
            root_logger.info(f"Logowanie do pliku włączone: {log_file_path_resolved}, Poziom: {logging.getLevelName(log_level_file)}")
        elif log_file: # Jeśli podano log_file, ale file_handler nie został dodany z powodu błędu
            root_logger.warning(f"Próbowano skonfigurować logowanie do pliku {log_file}, ale wystąpił błąd.")
        else:
            root_logger.info("Logowanie do pliku jest wyłączone (brak ścieżki).")

        if console_logging_enabled and any(isinstance(h, (logging.StreamHandler, RichHandler if RICH_LOGGING_AVAILABLE and RichHandler else logging.StreamHandler)) for h in root_logger.handlers):
             root_logger.info(f"Logowanie do konsoli włączone. Poziom: {logging.getLevelName(log_level_console)}")
        elif console_logging_enabled: # Próbowano włączyć, ale nie dodano handlera
             root_logger.warning("Próbowano włączyć logowanie do konsoli, ale handler nie został pomyślnie dodany.")
        else:
             root_logger.info("Logowanie do konsoli jest wyłączone.")

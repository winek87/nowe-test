# start.py
import logging
import sys
from pathlib import Path
from datetime import datetime

from src.logger_configurator import LoggerConfigurator
from src.config_manager import ConfigManager, DEFAULT_CONFIG
from src.cli_display import CLIDisplay
from src.profiler import Profiler
from src.repair_profiler import RepairProfiler
from src.ffmpeg.ffmpeg_manager import FFmpegManager
from src.filesystem.path_resolver import PathResolver
from src.filesystem.job_state_manager import JobStateManager
from src.filesystem.directory_scanner import DirectoryScanner
from src.filesystem.damaged_files_manager import DamagedFilesManager
from src.system_monitor.resource_monitor import ResourceMonitor
from src.cli_handlers.main_router import MainRouter

def main():
    app_base_dir = Path(__file__).resolve().parent 
    config_manager = ConfigManager(app_base_dir_override=app_base_dir)

    log_level_file_str = config_manager.get_config_value('general', 'log_level_file', DEFAULT_CONFIG['general']['log_level_file'])
    log_level_console_str = config_manager.get_config_value('general', 'log_level_console', DEFAULT_CONFIG['general']['log_level_console'])
    log_level_file_int = logging.getLevelName(log_level_file_str.upper()) if isinstance(log_level_file_str, str) else logging.INFO
    log_level_console_int = logging.getLevelName(log_level_console_str.upper()) if isinstance(log_level_console_str, str) else logging.INFO
    console_logging_enabled_bool = config_manager.get_config_value('general', 'console_logging_enabled', DEFAULT_CONFIG['general']['console_logging_enabled'])
    clear_log_on_start_bool = config_manager.get_config_value('general', 'clear_log_on_start', DEFAULT_CONFIG['general']['clear_log_on_start'])
    log_file_full_path = config_manager.get_log_file_full_path()

    LoggerConfigurator.setup_logging(
        log_file=log_file_full_path,
        log_level_file=log_level_file_int if isinstance(log_level_file_int, int) else logging.INFO,
        log_level_console=log_level_console_int if isinstance(log_level_console_int, int) else logging.INFO,
        console_logging_enabled=console_logging_enabled_bool,
        clear_log_on_start=clear_log_on_start_bool
    )

    logger = logging.getLogger(__name__) 
    logger.info("="*50 + "\nAplikacja Video Transcoder NG uruchomiona.\n" + "="*50)
    logger.info(f"Używany plik konfiguracyjny: {config_manager.config_file_path.resolve()}")
    if log_file_full_path and log_file_full_path.exists():
        logger.info(f"Plik logu: {log_file_full_path.resolve()}")
    elif log_file_full_path:
         logger.warning(f"Skonfigurowano plik logu ({log_file_full_path.resolve()}), ale może nie zostać utworzony z powodu wcześniejszego błędu.")
    if not console_logging_enabled_bool:
        logger.info("Logowanie na konsolę jest WYŁĄCZONE w konfiguracji.")

    resource_monitor = ResourceMonitor()
    display = CLIDisplay(resource_monitor=resource_monitor)
    
    progress_bar_width_val = config_manager.get_config_value('ui', 'progress_bar_width', DEFAULT_CONFIG['ui']['progress_bar_width'])
    progress_bar_ui_width = int(progress_bar_width_val) if isinstance(progress_bar_width_val, (int, float, str)) and str(progress_bar_width_val).isdigit() else 40
    display.set_progress_bar_width(progress_bar_ui_width)

    ffmpeg_manager = FFmpegManager(config_manager, display_progress_callback=display.display_progress_bar)
    path_resolver = PathResolver(config_manager) # Inicjalizacja PathResolver
    job_state_manager = JobStateManager(config_manager)
    damaged_files_manager = DamagedFilesManager(config_manager, ffmpeg_manager) # Inicjalizacja DamagedFilesManager
    
    # POPRAWKA: Przekaż path_resolver i damaged_files_manager do DirectoryScanner
    directory_scanner = DirectoryScanner(
        config_manager, 
        ffmpeg_manager, 
        path_resolver, 
        damaged_files_manager
    )
    
    profiler = Profiler(config_manager)
    profiler._create_default_profile_if_empty() 
    
    repair_profiler_instance = RepairProfiler(config_manager)

    if not resource_monitor.is_available() and console_logging_enabled_bool:
        display.display_warning(
            "Biblioteka 'psutil' nie jest zainstalowana lub dostępna. "
            "Monitorowanie zasobów systemowych będzie niedostępne."
        )

    main_router = MainRouter(
        display=display, config_manager=config_manager, profiler=profiler,
        ffmpeg_manager=ffmpeg_manager, path_resolver=path_resolver,
        job_state_manager=job_state_manager, directory_scanner=directory_scanner,
        damaged_files_manager=damaged_files_manager,
        resource_monitor=resource_monitor,
        repair_profiler=repair_profiler_instance
    )

    try:
        main_router.run_main_loop()
    except SystemExit as e:
        logger.info(f"Aplikacja zakończona z kodem: {e.code}")
    except KeyboardInterrupt:
        logger.info("Aplikacja przerwana przez użytkownika (Ctrl+C) na najwyższym poziomie.")
        if hasattr(display, 'finalize_progress_display') and hasattr(display, '_displaying_progress') and display._displaying_progress:
            display.finalize_progress_display()
        if 'display' in locals() and display is not None:
             display.display_info("\nAplikacja zakończona.")
    except Exception as e:
        logger.critical(f"Nieobsłużony wyjątek na najwyższym poziomie aplikacji: {e}", exc_info=True)
        if hasattr(display, 'finalize_progress_display') and hasattr(display, '_displaying_progress') and display._displaying_progress:
            display.finalize_progress_display()
        if 'display' in locals() and display is not None:
            display.display_error(f"Wystąpił nieoczekiwany, krytyczny błąd aplikacji: {e}")
            display.display_error("Sprawdź plik logu, aby uzyskać więcej informacji.")
        else:
            print(f"KRYTYCZNY BŁĄD APLIKACJI: {e}", file=sys.stderr)
            print("Sprawdź plik logu (jeśli został utworzony), aby uzyskać więcej informacji.", file=sys.stderr)
        sys.exit(1)

    logger.info("="*50 + "\nAplikacja Video Transcoder NG zakończona.\n" + "="*50)
    if 'display' in locals() and display is not None:
        display.display_info("\nDziękujemy za skorzystanie z aplikacji!")

if __name__ == "__main__":
    main()

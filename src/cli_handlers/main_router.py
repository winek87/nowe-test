# src/cli_handlers/main_router.py
import logging
import sys
from datetime import datetime
import time
from typing import Optional, List, Dict, Any 
import re

try:
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.console import Console
    from rich.layout import Layout
    from rich.progress_bar import ProgressBar
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Live, Table, Panel, Text, Console, Layout, ProgressBar = (None,) * 7 # type: ignore


from ..cli_display import CLIDisplay
from ..config_manager import ConfigManager
from ..profiler import Profiler
from ..repair_profiler import RepairProfiler # Upewnij się, że ten import jest
from ..ffmpeg.ffmpeg_manager import FFmpegManager
from ..filesystem.path_resolver import PathResolver
from ..filesystem.job_state_manager import JobStateManager
from ..filesystem.directory_scanner import DirectoryScanner
from ..filesystem.damaged_files_manager import DamagedFilesManager
from ..system_monitor.resource_monitor import ResourceMonitor

from .job_handler import JobCLIHandler
from .profile_handler import ProfileCLIHandler
from .settings_handler import SettingsCLIHandler
from .damaged_files_cli_handler import DamagedFilesCLIHandler
from .. import cli_styles as styles


logger = logging.getLogger(__name__)

class MainRouter:
    def __init__(self,
                 display: CLIDisplay, config_manager: ConfigManager, profiler: Profiler,
                 ffmpeg_manager: FFmpegManager, path_resolver: PathResolver,
                 job_state_manager: JobStateManager, directory_scanner: DirectoryScanner,
                 damaged_files_manager: DamagedFilesManager, resource_monitor: ResourceMonitor,
                 repair_profiler: RepairProfiler # <-- DODANY ARGUMENT
                ):
        logger.debug("MainRouter: Inicjalizacja rozpoczęta.")
        self.display = display; self.config_manager = config_manager; self.profiler = profiler
        self.ffmpeg_manager = ffmpeg_manager; self.resource_monitor = resource_monitor
        self.console = Console() if RICH_AVAILABLE and Console else None
        
        self.repair_profiler = repair_profiler # <-- ZAPISZ INSTANCJĘ

        self.job_handler = JobCLIHandler(display, config_manager, profiler, ffmpeg_manager, path_resolver, job_state_manager, directory_scanner, damaged_files_manager, resource_monitor)
        self.profile_handler = ProfileCLIHandler(display, config_manager, profiler)
        # Przekaż repair_profiler do SettingsCLIHandler
        self.settings_handler = SettingsCLIHandler(
            display, config_manager, ffmpeg_manager, profiler, self.repair_profiler
        )
        # Przekaż repair_profiler do DamagedFilesCLIHandler
        self.damaged_files_handler = DamagedFilesCLIHandler(
            display, config_manager, damaged_files_manager,
            ffmpeg_manager, path_resolver, directory_scanner,
            repair_profiler=self.repair_profiler 
        )
        logger.debug("MainRouter: Inicjalizacja zakończona.")

    def run_main_loop(self):
        # ... (bez zmian od ostatniej poprawnej wersji - np. z odpowiedzi #66)
        logger.info("MainRouter: Uruchamianie głównej pętli aplikacji.")
        last_selected_main_menu_idx: Optional[int] = 0 
        try:
            while True:
                choice_key, returned_idx = self.display.display_main_menu(initial_selection_index=last_selected_main_menu_idx)
                last_selected_main_menu_idx = returned_idx 
                
                if self.job_handler.is_processing and choice_key not in ['0']:
                    self.display.display_warning("Zadanie transkodowania jest w toku. Poczekaj lub przerwij (Ctrl+C).")
                    self.display.press_enter_to_continue(); continue
                
                if not self._handle_main_menu_choice(choice_key):
                    break
        except KeyboardInterrupt:
            logger.info("MainRouter: Przerwanie przez użytkownika (Ctrl+C). Bezpieczne zamykanie.")
            if hasattr(self.display, 'finalize_progress_display') and hasattr(self.display, '_displaying_progress') and self.display._displaying_progress: 
                self.display.finalize_progress_display()
            if self.job_handler.is_processing and self.job_handler.current_job_state:
                job = self.job_handler.current_job_state; job.status = "Anulowano"; job.end_time = datetime.now(); job_err_msg = "\nZadanie anulowane przez użytkownika."
                if hasattr(job, 'processed_files') and job.processed_files:
                    for pf_item in job.processed_files:
                        if pf_item.status == "Przetwarzanie": pf_item.status = "Anulowano"; pf_item.end_time = datetime.now(); pf_item.error_message = (pf_item.error_message or "") + job_err_msg
                job.error_message = (job.error_message or "") + job_err_msg
                try: self.job_handler.job_state_manager.save_job_state(job); self.display.display_warning(f"Zadanie {job.job_id} anulowane, stan zapisany.")
                except Exception as save_e: logger.error(f"Błąd zapisu stanu zadania po anulowaniu: {save_e}", exc_info=True)
            else: self.display.display_info("Aplikacja zakończona przez użytkownika.")
        except Exception as e:
            logger.critical(f"MainRouter: Nieobsłużony krytyczny błąd w głównej pętli: {e}", exc_info=True)
            if hasattr(self.display, 'finalize_progress_display') and hasattr(self.display, '_displaying_progress') and self.display._displaying_progress: 
                self.display.finalize_progress_display()
            self.display.display_error(f"Wystąpił nieoczekiwany błąd krytyczny: {e}")
            if self.job_handler.is_processing and self.job_handler.current_job_state:
                job = self.job_handler.current_job_state; job.status = "Błąd krytyczny"; job.end_time = datetime.now(); errMsg = f"\nZadanie zakończone globalnym błędem aplikacji: {e}"
                if hasattr(job, 'processed_files') and job.processed_files:
                    for pf_item in job.processed_files:
                         if pf_item.status == "Przetwarzanie": pf_item.status = "Błąd krytyczny"; pf_item.end_time = datetime.now(); pf_item.error_message = (pf_item.error_message or "") + errMsg
                job.error_message = (job.error_message or "") + errMsg
                try: self.job_handler.job_state_manager.save_job_state(job)
                except Exception as save_e: logger.error(f"Błąd zapisu stanu zadania po błędzie krytycznym: {save_e}", exc_info=True)
            sys.exit(1)
        logger.info("MainRouter: Główna pętla aplikacji zakończona.")

    def _handle_main_menu_choice(self, choice: str) -> bool:
        # ... (bez zmian od ostatniej poprawnej wersji - np. z odpowiedzi #66)
        choice = choice.strip().lower(); logger.debug(f"MainRouter: Obsługa wyboru z menu głównego: '{choice}'")
        if choice != '11' and self.display: self.display.clear_screen()
        if choice == '1': self.job_handler.start_new_directory_scan_job_cli()
        elif choice == '2': self.job_handler.resume_last_job_cli()
        elif choice == '3': self.job_handler.display_last_job_state_cli()
        elif choice == '4': self.profile_handler.manage_profiles_menu()
        elif choice == '5': self.damaged_files_handler.scan_directory_for_damaged_files_cli()
        elif choice == '6': self.damaged_files_handler.attempt_repair_damaged_file_cli()
        elif choice == '7': self.damaged_files_handler.manage_damaged_files_menu()
        elif choice == '8': self.display.clear_screen(); self.display.display_config_dict(self.config_manager.get_config())
        elif choice == '9':
            log_path = self.config_manager.get_log_file_full_path(); self.display.clear_screen()
            if hasattr(self.display, '_display_framed_content_block'): self.display._display_framed_content_block(title=f"{styles.ICON_LOG} Ścieżka Pliku Logu {styles.ICON_LOG}", content_lines=[f"Aktualna ścieżka:", f"{styles.STYLE_CONFIG_VALUE}{log_path}{styles.ANSI_RESET}"]) # type: ignore
            else: self.display.display_info(f"Ścieżka pliku logu: {log_path}")
            self.display.press_enter_to_continue()
        elif choice == '10': self.settings_handler.manage_settings_menu()
        elif choice == '11':
            if RICH_AVAILABLE and self.console: self._run_system_monitor_loop_rich()
            else: self._run_system_monitor_loop_legacy()
        elif choice == '0': self.display.display_info(f"{styles.ICON_EXIT} Wychodzenie z aplikacji..."); return False 
        else: self.display.display_warning("Nieprawidłowy wybór."); self.display.press_enter_to_continue()
        return True

    def _update_main_stats_panel(self) -> Panel: # type: ignore
        # ... (bez zmian od ostatniej poprawnej wersji - np. z odpowiedzi #66)
        main_table = Table(show_header=False, box=None, expand=True, padding=(0,1), show_edge=False); main_table.add_column("Zasób", style=styles.RICH_STYLE_SYSTEM_MONITOR_LABEL, justify="right", width=22); main_table.add_column("Wartość", style=styles.RICH_STYLE_SYSTEM_MONITOR_VALUE, overflow="fold"); cpu_usage=self.resource_monitor.get_cpu_usage(); ram_usage=self.resource_monitor.get_ram_usage(); cpu_stats=self.resource_monitor.get_cpu_stats(); cpu_temps_data=self.resource_monitor.get_cpu_temperatures(); rtc_battery=self.resource_monitor.get_raspberry_pi_rtc_battery_voltage(); system_uptime=self.resource_monitor.get_system_uptime(); load_average=self.resource_monitor.get_load_average(); process_count=self.resource_monitor.get_process_count(); network_stats=self.resource_monitor.get_network_io_stats(); cpu_usage_text = Text("N/A", style="dim") if cpu_usage is None else Text(f"{cpu_usage:.1f}%", style=(styles.RICH_STYLE_CPU_WYSOKIE if cpu_usage > 90 else styles.RICH_STYLE_CPU_SREDNIE if cpu_usage > 75 else styles.RICH_STYLE_CPU_NISKIE)); main_table.add_row("🖥️ Użycie CPU:", cpu_usage_text)
        if cpu_temps_data:
            all_temp_texts = [Text.assemble((f"{(entry.get('label','').strip() or name).replace('Temp','').replace('Package id 0','CPU').replace('_',' ').title()}: ", styles.RICH_STYLE_SYSTEM_MONITOR_LABEL), (f"{entry.get('current'):.1f}°C" if entry.get('current') is not None else "N/A", ("bold red" if float(entry.get('current',0)) > 85 else "bold yellow" if float(entry.get('current',0)) > 70 else "green") if entry.get('current') is not None else "dim")) for name, entries in cpu_temps_data.items() for entry in entries] 
            if all_temp_texts: main_table.add_row("🌡️ Temp. CPU:", Text("\n").join(all_temp_texts) if len(all_temp_texts) > 3 else Text(" | ").join(all_temp_texts))
            else: main_table.add_row("🌡️ Temp. CPU:", Text("N/A", style="dim"))
        else: main_table.add_row("🌡️ Temp. CPU:", Text("N/A", style="dim"))
        ram_text = Text("N/A", style="dim") if not ram_usage else Text.assemble((f"{ram_usage['percent']:.1f}%", (styles.RICH_STYLE_RAM_WYSOKIE if ram_usage['percent'] > 90 else styles.RICH_STYLE_RAM_SREDNIE if ram_usage['percent'] > 75 else styles.RICH_STYLE_RAM_NISKIE)), (f" (U:{ram_usage['used_gb']:.1f}/C:{ram_usage['total_gb']:.1f}GB)", styles.RICH_STYLE_SYSTEM_MONITOR_VALUE)); main_table.add_row("🧠 Użycie RAM:", ram_text)
        if cpu_stats: main_table.add_row("🛠️ Rdzenie CPU:", Text(f"L:{cpu_stats.get('liczba_rdzeni_logicznych','N/A')},F:{cpu_stats.get('liczba_rdzeni_fizycznych','N/A')}",style=styles.RICH_STYLE_SYSTEM_MONITOR_VALUE)); main_table.add_row("⏱️ Taktowanie:", Text(f"{cpu_stats.get('aktualna_czestotliwosc_mhz','N/A')}MHz",style=styles.RICH_STYLE_SYSTEM_MONITOR_VALUE))
        if rtc_battery and "N/A" not in rtc_battery : main_table.add_row("🔋 Bateria RTC:", Text(str(rtc_battery), style="red" if "V" in rtc_battery and float(rtc_battery.split('V')[0]) < 2.5 else "yellow" if "V" in rtc_battery and float(rtc_battery.split('V')[0]) < 2.7 else styles.RICH_STYLE_SYSTEM_MONITOR_VALUE))
        if system_uptime and "N/A" not in system_uptime : main_table.add_row("⏳ Czas działania:", Text(system_uptime,style=styles.RICH_STYLE_SYSTEM_MONITOR_VALUE))
        if load_average : main_table.add_row("📈 Śr. obciążenie:", Text(load_average,style=styles.RICH_STYLE_SYSTEM_MONITOR_VALUE))
        if process_count is not None : main_table.add_row("⚙️ Procesy:", Text(str(process_count),style=styles.RICH_STYLE_SYSTEM_MONITOR_VALUE))
        if network_stats : main_table.add_row("📶 Sieć (W/O Mbps | GB):", Text(f"{network_stats['sent_rate_mbps']}/{network_stats['recv_rate_mbps']} | {network_stats['total_sent_gb']}/{network_stats['total_recv_gb']}",style=styles.RICH_STYLE_SYSTEM_MONITOR_VALUE))
        return Panel(main_table, title="[bold blue]📊 CPU / RAM / Sensory / System[/bold blue]", border_style=styles.RICH_STYLE_PANEL_BORDER, title_align="left", expand=True)

    def _update_disks_panel(self, disk_usages: Optional[List[Dict[str, Any]]]) -> Panel: # type: ignore
        # ... (bez zmian od ostatniej poprawnej wersji - np. z odpowiedzi #66)
        if not disk_usages: return Panel(Text("Brak danych o dyskach.", justify="center", style="dim"), title="[bold blue]💾 Dyski[/bold blue]", border_style=styles.RICH_STYLE_PANEL_BORDER, expand=True)
        disks_table = Table(box=None, expand=True, padding=(0,0),show_edge=False,show_lines=False); disks_table.add_column("Partycja",style=styles.RICH_STYLE_DISK_LABEL_DEVICE, overflow="fold",min_width=15,ratio=20); disks_table.add_column("Punkt Mont.",style=styles.RICH_STYLE_DISK_LABEL_MOUNT, overflow="fold",min_width=15,ratio=30); disks_table.add_column("FS",style=styles.RICH_STYLE_DISK_LABEL_FSTYPE,width=7,ratio=10); disks_table.add_column("Użycie",justify="center",style=styles.RICH_STYLE_SYSTEM_MONITOR_VALUE,width=7,ratio=8); disks_table.add_column("Pasek",width=22,ratio=15,justify="left"); disks_table.add_column("Wolne",style=styles.RICH_STYLE_DISK_FREE_GOOD,justify="right",width=9,ratio=9); disks_table.add_column("Rozmiar",style=styles.RICH_STYLE_DISK_LABEL_SIZE,justify="right",width=18,ratio=18)
        for disk in disk_usages:
            p = disk['percent_used']; bf=styles.RICH_STYLE_DISK_FREE_GOOD if p<75 else styles.RICH_STYLE_DISK_FREE_LOW if p<90 else "red"; bar = ProgressBar(total=100,completed=p,width=20,style="on grey30",complete_style=bf,finished_style=bf); disks_table.add_row(disk['device'][-15:],disk['mountpoint'][-22:],disk['fstype'],f"{p:.1f}%",bar,Text(f"{disk['free_gb']:.1f}G",style=bf),f"({disk['used_gb']:.1f}/{disk['total_gb']:.1f}G)")
        return Panel(disks_table, title="[bold blue]💾 Dyski[/bold blue]", border_style=styles.RICH_STYLE_PANEL_BORDER, expand=True)

    def _generate_monitor_layout(self) -> Layout: # type: ignore
        # ... (bez zmian od ostatniej poprawnej wersji - np. z odpowiedzi #66)
        layout = Layout(name="root"); layout.split_column(Layout(name="header",size=3),Layout(name="main_stats",ratio=1),Layout(name="disks",ratio=1),Layout(name="footer",size=1)); layout["header"].update(Panel(Text("🔧 Monitor Zasobów Systemowych 🖥️",justify="center",style=styles.RICH_STYLE_TABLE_TITLE))); layout["footer"].update(Text("Naciśnij Ctrl+C aby wrócić", justify="center",style=styles.RICH_STYLE_FOOTER_TEXT)); return layout

    def _run_system_monitor_loop_rich(self):
        # ... (bez zmian od ostatniej poprawnej wersji - np. z odpowiedzi #66)
        if not self.resource_monitor.is_available(): self.display.display_error("Monitor zasobów jest niedostępny (psutil)."); self.display.press_enter_to_continue(); return
        if not RICH_AVAILABLE or not self.console: self.display.display_error("Biblioteka Rich niedostępna. Użyj trybu legacy."); self._run_system_monitor_loop_legacy(); return
        layout = self._generate_monitor_layout(); refresh_rate = float(self.config_manager.get_config_value("ui", "rich_monitor_refresh_rate", 2.0)); disk_interval = float(self.config_manager.get_config_value("ui", "rich_monitor_disk_refresh_interval", 5.0)); last_disk_refresh = 0.0
        try:
            layout["main_stats"].update(self._update_main_stats_panel()); layout["disks"].update(self._update_disks_panel(self.resource_monitor.get_disk_usage_info()))
            with Live(layout, console=self.console, screen=True, transient=True, refresh_per_second=refresh_rate, vertical_overflow="visible") as live: 
                while True:
                    current_time = time.time(); layout["main_stats"].update(self._update_main_stats_panel())
                    if current_time - last_disk_refresh >= disk_interval: layout["disks"].update(self._update_disks_panel(self.resource_monitor.get_disk_usage_info())); last_disk_refresh = current_time
                    time.sleep(0.05) 
        except KeyboardInterrupt: 
            if self.display: self.display.clear_screen(); logger.info("Monitor Rich przerwany.")
        except Exception as e: 
            if self.display: self.display.clear_screen(); logger.error(f"Błąd Rich monitora: {e}", exc_info=True)
            if self.display: self.display.display_error(f"Błąd Rich monitora: {e}")
        finally:
             if self.display: self.display.clear_screen()

    def _run_system_monitor_loop_legacy(self):
        # ... (bez zmian od ostatniej poprawnej wersji - np. z odpowiedzi #66)
        if not self.resource_monitor.is_available(): self.display.display_error("Monitor zasobów niedostępny (psutil)."); self.display.press_enter_to_continue(); return
        refresh_interval = float(self.config_manager.get_config_value("ui", "legacy_monitor_refresh_interval", 2.0)); refresh_interval = max(0.5, refresh_interval)
        try:
            while True:
                self.display.clear_screen(); cpu_u,ram_u,cpu_s_v,cpu_t,rtc_b,disk_u_i,sys_u,load_a,proc_c,net_s = (self.resource_monitor.get_cpu_usage(),self.resource_monitor.get_ram_usage(),self.resource_monitor.get_cpu_stats(),self.resource_monitor.get_cpu_temperatures(),self.resource_monitor.get_raspberry_pi_rtc_battery_voltage(),self.resource_monitor.get_disk_usage_info(),self.resource_monitor.get_system_uptime(),self.resource_monitor.get_load_average(),self.resource_monitor.get_process_count(),self.resource_monitor.get_network_io_stats()); self.display.display_system_resources(cpu_u,ram_u,cpu_s_v,disk_u_i,cpu_t,rtc_b,sys_u,load_a,proc_c,net_s); time.sleep(refresh_interval)
        except KeyboardInterrupt: 
            if self.display: self.display.clear_screen(); logger.info("Monitor legacy przerwany.")
        except Exception as e: 
            if self.display: self.display.clear_screen(); logger.error(f"Błąd monitora legacy: {e}", exc_info=True)
            if self.display: self.display.display_error(f"Błąd monitora legacy: {e}")
        finally:
            if self.display: self.display.clear_screen()

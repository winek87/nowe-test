# src/system_monitor/resource_monitor.py
import logging
from typing import Dict, Any, Optional, List, Union 
import subprocess 
from pathlib import Path 
import os 
import time 

try:
    import psutil
except ImportError:
    psutil = None 

logger = logging.getLogger(__name__)

class ResourceMonitor:
    # ... (__init__, is_available, get_cpu_usage, get_ram_usage, get_cpu_stats, 
    #      get_cpu_temperatures, get_raspberry_pi_rtc_battery_voltage, 
    #      get_system_uptime, get_load_average, get_process_count, get_network_io_stats - bez zmian) ...
    def __init__(self):
        if psutil is None: logger.warning("Biblioteka psutil nie została znaleziona."); return
        logger.debug("ResourceMonitor zainicjalizowany.")
        if hasattr(psutil, 'net_io_counters'): self.initial_net_io = psutil.net_io_counters(); self.last_net_io = self.initial_net_io; self.last_net_io_time = time.time()
        else: self.initial_net_io = None; self.last_net_io = None; self.last_net_io_time = None; logger.warning("psutil.net_io_counters() niedostępne.")
    def is_available(self) -> bool: return psutil is not None
    def get_cpu_usage(self) -> Optional[float]:
        if not self.is_available(): return None
        try: return psutil.cpu_percent(interval=0.1) 
        except Exception as e: logger.error(f"Błąd CPU: {e}", exc_info=True); return None
    def get_ram_usage(self) -> Optional[Dict[str, Any]]:
        if not self.is_available(): return None
        try: mem = psutil.virtual_memory(); return {"total_gb": round(mem.total / (1024**3), 2), "available_gb": round(mem.available / (1024**3), 2), "percent": mem.percent, "used_gb": round(mem.used / (1024**3), 2), "free_gb": round(mem.free / (1024**3), 2)}
        except Exception as e: logger.error(f"Błąd RAM: {e}", exc_info=True); return None
    def get_cpu_stats(self) -> Optional[Dict[str, Any]]:
        if not self.is_available(): return None
        try:
            cpu_stats = {"liczba_rdzeni_logicznych": psutil.cpu_count(logical=True), "liczba_rdzeni_fizycznych": psutil.cpu_count(logical=False), "aktualna_czestotliwosc_mhz": "N/A", "min_czestotliwosc_mhz": "N/A", "max_czestotliwosc_mhz": "N/A"}
            if hasattr(psutil, 'cpu_freq'):
                try:
                    freq = psutil.cpu_freq()
                    if freq: cpu_stats["aktualna_czestotliwosc_mhz"] = freq.current if hasattr(freq, 'current') and freq.current is not None else "N/A"; cpu_stats["min_czestotliwosc_mhz"] = freq.min if hasattr(freq, 'min') and freq.min is not None else "N/A"; cpu_stats["max_czestotliwosc_mhz"] = freq.max if hasattr(freq, 'max') and freq.max is not None else "N/A"
                except Exception as freq_e: logger.warning(f"Nie można pobrać częstotliwości CPU: {freq_e}")
            else: logger.warning("psutil.cpu_freq() niedostępne.")
            return cpu_stats
        except Exception as e: logger.error(f"Błąd CPU stats: {e}", exc_info=True); return None
    def get_cpu_temperatures(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        if not self.is_available() or not hasattr(psutil, 'sensors_temperatures'): logger.debug("psutil.sensors_temperatures() niedostępne."); return None
        try:
            temps = psutil.sensors_temperatures(); 
            if not temps: logger.debug("psutil.sensors_temperatures() brak danych."); return None
            relevant_temps: Dict[str, List[Dict[str, Any]]] = {}
            for name, entries in temps.items():
                if any(keyword in name.lower() for keyword in ['cpu', 'core', 'k10', 'thermal_zone']) or name == 'cpu-thermal':
                    cleaned_entries = [{"label": entry.label or name, "current": entry.current, "high": entry.high, "critical": entry.critical} for entry in entries if entry.current is not None]
                    if cleaned_entries: relevant_temps[name] = cleaned_entries
            # ... (reszta logiki RPi temp bez zmian)
            rpi_temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
            if rpi_temp_path.exists():
                try:
                    with open(rpi_temp_path, 'r') as f: temp_milli_c = int(f.read().strip()); temp_c = temp_milli_c / 1000.0
                    rpi_sensor_name = "cpu-thermal"; 
                    if rpi_sensor_name not in relevant_temps: relevant_temps[rpi_sensor_name] = []
                    found = False
                    for entry in relevant_temps[rpi_sensor_name]:
                        if entry["label"] == "thermal_zone0" or entry["label"] == rpi_sensor_name: entry["current"] = temp_c; found = True; break
                    if not found: relevant_temps[rpi_sensor_name].append({"label": "thermal_zone0", "current": temp_c, "high": None, "critical": None})
                    logger.debug(f"Odczyt RPi temp z {rpi_temp_path}: {temp_c}°C")
                except Exception as e_rpi_temp: logger.warning(f"Błąd odczytu RPi temp z {rpi_temp_path}: {e_rpi_temp}")
            return relevant_temps if relevant_temps else None
        except Exception as e: logger.error(f"Błąd temperatur CPU: {e}", exc_info=True); return None
    def get_raspberry_pi_rtc_battery_voltage(self) -> Optional[str]:
        # ... (bez zmian)
        if not self.is_available(): return None
        try:
            process_check = subprocess.run(['which', 'vcgencmd'], capture_output=True, text=True, check=False)
            if process_check.returncode != 0 or not process_check.stdout.strip(): logger.info("'vcgencmd' nie znalezione."); return "N/A (vcgencmd?)"
            process = subprocess.run(['vcgencmd', 'pmic_read_adc', 'BATT_V'], capture_output=True, text=True, timeout=5, check=False)
            if process.returncode == 0 and process.stdout:
                output_line = process.stdout.strip()
                if "volt" in output_line and "=" in output_line and "V" in output_line:
                    try: voltage_str = output_line.split('=')[1].split('V')[0]; voltage_float = float(voltage_str); logger.debug(f"RTC BATT_V: {voltage_float:.2f}V"); return f"{voltage_float:.2f}V"
                    except (IndexError, ValueError) as e_parse: logger.error(f"Parse error vcgencmd BATT_V: '{output_line}'. {e_parse}"); return "N/A (parse)"
                else: logger.warning(f"Format error vcgencmd BATT_V: '{output_line}'"); return "N/A (format?)"
            else: logger.warning(f"vcgencmd BATT_V failed. Code: {process.returncode}, Stderr: {process.stderr.strip()}"); return "N/A (vcgencmd error)"
        except Exception as e: logger.error(f"Błąd RTC vcgencmd: {e}", exc_info=True); return "N/A (exception)"
    def get_system_uptime(self) -> Optional[str]:
        # ... (bez zmian)
        if not self.is_available(): return None
        try:
            boot_time_timestamp = psutil.boot_time(); current_time_timestamp = time.time(); uptime_seconds = current_time_timestamp - boot_time_timestamp
            days = int(uptime_seconds // (24 * 3600)); uptime_seconds %= (24 * 3600); hours = int(uptime_seconds // 3600); uptime_seconds %= 3600; minutes = int(uptime_seconds // 60)
            parts = []; 
            if days > 0: parts.append(f"{days}d")
            if hours > 0: parts.append(f"{hours}g")
            if minutes > 0 or (days == 0 and hours == 0) : parts.append(f"{minutes}m") 
            return " ".join(parts) if parts else "mniej niż minuta"
        except Exception as e: logger.error(f"Błąd uptime: {e}", exc_info=True); return "N/A"
    def get_load_average(self) -> Optional[str]:
        # ... (bez zmian)
        if not self.is_available() or not hasattr(os, 'getloadavg'): return None 
        try: load1, load5, load15 = os.getloadavg(); return f"{load1:.2f}, {load5:.2f}, {load15:.2f}"
        except Exception as e: logger.error(f"Błąd load avg: {e}", exc_info=True); return "N/A"
    def get_process_count(self) -> Optional[int]:
        # ... (bez zmian)
        if not self.is_available(): return None
        try: return len(psutil.pids())
        except Exception as e: logger.error(f"Błąd process count: {e}", exc_info=True); return None
    def get_network_io_stats(self) -> Optional[Dict[str, str]]:
        # ... (bez zmian)
        if not self.is_available() or not hasattr(psutil, 'net_io_counters'): logger.warning("psutil.net_io_counters() niedostępne."); return None
        current_time = time.time(); current_net_io = psutil.net_io_counters()
        if not hasattr(self, 'last_net_io') or self.last_net_io is None: self.last_net_io = current_net_io; self.last_net_io_time = current_time
        if self.last_net_io_time is None : self.last_net_io_time = current_time # Upewnij się, że jest zainicjalizowany
        time_delta = current_time - self.last_net_io_time
        if time_delta <= 0.01: return {"sent_rate_mbps": "...", "recv_rate_mbps": "...", "total_sent_gb": f"{current_net_io.bytes_sent / (1024**3):.2f}", "total_recv_gb": f"{current_net_io.bytes_recv / (1024**3):.2f}"}
        bytes_sent_delta = current_net_io.bytes_sent - self.last_net_io.bytes_sent; bytes_recv_delta = current_net_io.bytes_recv - self.last_net_io.bytes_recv
        sent_rate_mbps = (bytes_sent_delta * 8) / (1024**2) / time_delta; recv_rate_mbps = (bytes_recv_delta * 8) / (1024**2) / time_delta
        self.last_net_io = current_net_io; self.last_net_io_time = current_time
        return {"sent_rate_mbps": f"{sent_rate_mbps:.2f}", "recv_rate_mbps": f"{recv_rate_mbps:.2f}", "total_sent_gb": f"{current_net_io.bytes_sent / (1024**3):.2f}", "total_recv_gb": f"{current_net_io.bytes_recv / (1024**3):.2f}"}

    def get_specific_disk_usage(self, path: Union[str, Path]) -> Optional[Dict[str, Any]]:
        """Zwraca informacje o wykorzystaniu dysku dla podanej ścieżki."""
        if not self.is_available(): return None
        try:
            resolved_path = Path(path).expanduser().resolve()
            # Aby uzyskać informacje o partycji, na której leży ścieżka,
            # musimy znaleźć punkt montowania. Możemy przejść w górę drzewa katalogów.
            # Jednak psutil.disk_usage(str(resolved_path)) powinno zadziałać bezpośrednio.
            usage = psutil.disk_usage(str(resolved_path))
            return {
                "path": str(resolved_path), # Ścieżka, dla której sprawdzono
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent_used": usage.percent
            }
        except (FileNotFoundError, PermissionError, OSError) as e:
            logger.warning(f"Nie można uzyskać informacji o wykorzystaniu dla ścieżki '{path}': {e}")
            return None
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas sprawdzania dysku dla '{path}': {e}", exc_info=True)
            return None

    def get_disk_usage_info(self) -> Optional[List[Dict[str, Any]]]:
        # ... (bez zmian, jak w ostatniej pełnej poprawnej wersji z wyłączonym logowaniem diagnostycznym) ...
        if not self.is_available(): return None
        disk_info_list: List[Dict[str, Any]] = [];
        try:
            try: partitions_to_scan = psutil.disk_partitions(all=True)
            except Exception as e_part: logger.error(f"Błąd odczytu partycji z psutil.disk_partitions(all=True): {e_part}"); return None 
            common_pseudo_fs = ['tmpfs', 'squashfs', 'devtmpfs', 'overlay', 'autofs', 'efivarfs', 'fuse.gvfsd-fuse', 'fuse.portal', 'fusectl', 'pstore', 'configfs', 'debugfs', 'securityfs', 'sysfs', 'proc', 'devpts', 'hugetlbfs', 'binfmt_misc', 'cgroup', 'cgroup2', 'mqueue', 'tracefs', 'ramfs']
            ignored_mount_prefixes = ['/snap/', '/var/lib/docker', '/boot/efi', '/run/user', '/run/lock', '/sys/']
            for p in partitions_to_scan: 
                if p.fstype.lower() in common_pseudo_fs: logger.debug(f"Filtrowanie (pseudo-fs): {p.device} ({p.fstype}) w {p.mountpoint}"); continue
                skip = False
                for prefix in ignored_mount_prefixes:
                    if p.mountpoint.startswith(prefix): logger.debug(f"Filtrowanie (prefix): {p.device} ({p.mountpoint})"); skip = True; break
                if skip: continue
                if p.device.startswith('/dev/loop') and not p.fstype: logger.debug(f"Filtrowanie (loop bez fs): {p.device}"); continue
                current_fstype = p.fstype if p.fstype else "unknown"
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    if usage.total == 0: logger.debug(f"Pomijanie partycji z zerowym rozmiarem całkowitym: {p.mountpoint}"); continue
                    disk_info_list.append({"device": p.device, "mountpoint": p.mountpoint, "fstype": current_fstype, "total_gb": round(usage.total / (1024**3), 2), "used_gb": round(usage.used / (1024**3), 2), "free_gb": round(usage.free / (1024**3), 2), "percent_used": usage.percent})
                except (FileNotFoundError, PermissionError, OSError) as e_usage: logger.warning(f"Nie można uzyskać informacji o wykorzystaniu dla {p.mountpoint} ({p.device}, {current_fstype}): {e_usage}")
                except Exception as e_usage_other: logger.error(f"Nieoczekiwany błąd info o dysku dla {p.mountpoint}: {e_usage_other}", exc_info=True)
            if not disk_info_list: logger.warning("Nie znaleziono partycji dyskowych do wyświetlenia po filtrowaniu.")
            return disk_info_list
        except Exception as e: logger.error(f"Błąd pobierania informacji o dyskach: {e}", exc_info=True); return None

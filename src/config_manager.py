# src/config_manager.py
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Union, Optional, List
import os
import sys
import shutil
import copy
from datetime import datetime
import json

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    'general': {
        'log_level_file': "INFO", 'log_level_console': "INFO",
        'console_logging_enabled': True, 'clear_log_on_start': True,
        'recursive_scan': False, 'active_profile_id': None,
    },
    'paths': {
        'main_config_file': 'config/config.yaml', 'profiles_file': 'profiles/default.json',
        'repair_profiles_file': 'profiles/repair_profiles.json', 'job_state_dir': '.app_data/job_state', 
        'default_output_directory': 'output/processed_videos', 'default_repaired_directory': 'output/repaired_videos',
        'log_file': 'logs/app.log', 'last_used_source_directory': None, 'last_used_single_file_path': None,
    },
    'ffmpeg': {
        'ffmpeg_path': 'ffmpeg', 'ffprobe_path': 'ffprobe', 'mkvmerge_path': 'mkvmerge',
        'enable_dynamic_timeout': True, 'dynamic_timeout_multiplier': 2.0,
        'dynamic_timeout_buffer_seconds': 300, 'dynamic_timeout_min_seconds': 600,
        'fixed_timeout_seconds': 86400,
    },
    'processing': {
        'error_handling': 'skip', 'output_file_exists': 'rename',
        'rename_pattern': '{original_stem}_{profile_name}_{timestamp}',
        'repair_rename_pattern': '{original_stem}_repaired_{timestamp}',
        'delete_original_on_success': False,
        'supported_file_extensions': [ '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.mpg', '.mpeg', '.ts', '.vob', '.mts', '.m2ts'],
        'verify_repaired_files': True, 'auto_repair_on_suspicion': True,
        'repair_timeout_seconds': 300,
        'repair_options': {
            'attempt_sequentially': True, 'use_custom_ffmpeg_repair_profiles': True,
            'enabled_ffmpeg_profile_ids': [],      
            'builtin_strategies_config': { 
                'mkvmerge_remux': { 'enabled': True, 'name': "MKVToolNix (Remuks MKV)", 'description': "Remuksowanie pliku MKV za pomocą mkvmerge (tylko dla .mkv)."}
            }
        }
    },
    'ui': {
        'datetime_format': '%Y-%m-%d %H:%M:%S', 'progress_bar_width': 40,
        'rich_monitor_refresh_rate': 2.0, 'rich_monitor_disk_refresh_interval': 5.0,
        'legacy_monitor_refresh_interval': 2.0, 'delay_between_files_seconds': 1.0,
    }
}

_SENTINEL = object() 

def _get_nested_value(data_dict: Dict, keys: List[str], dict_name_for_log: str = "data_dict", default_return: Any = _SENTINEL) -> Any:
    current = data_dict
    path_traversed_for_debug = []
    # logger.debug(f"_GET_NESTED ({dict_name_for_log}): Próba odczytu kluczy {keys}. Początkowe klucze w data_dict: {list(data_dict.keys())[:10] if isinstance(data_dict, dict) else 'Not a dict'}")
    try:
        for i, key_part in enumerate(keys):
            path_traversed_for_debug.append(key_part)
            if not isinstance(current, dict):
                # logger.debug(f"_GET_NESTED ({dict_name_for_log}): Oczekiwano dict na '{'.'.join(path_traversed_for_debug[:-1])}', ale znaleziono {type(current)} przy próbie dostępu do '{key_part}'.")
                return default_return
            # logger.debug(f"_GET_NESTED ({dict_name_for_log}): Dostęp do '{key_part}' w '{'.'.join(path_traversed_for_debug[:-1]) if path_traversed_for_debug[:-1] else 'root'}'. Klucze na tym poziomie: {list(current.keys())}")
            current = current[key_part]
        # logger.debug(f"_GET_NESTED ({dict_name_for_log}): Klucz '{'.'.join(keys)}' znaleziony. Wartość: {repr(current)}")
        return current
    except KeyError:
        # logger.debug(f"_GET_NESTED ({dict_name_for_log}): KeyError dla '{key_part}' (ostatni próbowany) na ścieżce '{'.'.join(path_traversed_for_debug)}'. Dostępne klucze: {list(current.keys()) if isinstance(current,dict) else 'Not a dict'}")
        return default_return
    except TypeError as e: 
        # logger.debug(f"_GET_NESTED ({dict_name_for_log}): TypeError na '{'.'.join(path_traversed_for_debug)}', current to {type(current)}. Błąd: {e}")
        return default_return

class ConfigManager:
    # ... (metody __init__ do _merge_configs jak w odpowiedzi #71, z poprawioną logiką _get_nested_value powyżej) ...
    def __init__(self, config_file_path_override: Optional[Union[str, Path]] = None, app_base_dir_override: Optional[Union[str, Path]] = None):
        logger.debug("ConfigManager: Inicjalizacja rozpoczęta.")
        self._config: Dict[str, Any] = {}
        if app_base_dir_override: self.app_base_dir: Path = Path(app_base_dir_override).expanduser().resolve()
        else: self.app_base_dir: Path = Path.cwd() 
        logger.info(f"ConfigManager: Bazowy katalog aplikacji: {self.app_base_dir}")
        if config_file_path_override: self.config_file_path: Path = Path(config_file_path_override).expanduser().resolve()
        else: default_rel_path_str = DEFAULT_CONFIG['paths']['main_config_file']; self.config_file_path = (self.app_base_dir / default_rel_path_str).resolve()
        logger.info(f"ConfigManager: Docelowy plik konfiguracyjny: {self.config_file_path}")
        self._load_default_config_internal() 
        self.load_config_from_file_and_merge() 
        logger.debug(f"ConfigManager __init__: id(self._config) = {id(self._config)}")
        logger.debug("ConfigManager: Inicjalizacja zakończona.")

    def _deep_copy_config(self, config_dict: Dict[str, Any]) -> Dict[str, Any]: return copy.deepcopy(config_dict)
    def _load_default_config_internal(self):
        logger.debug("ConfigManager: Ładowanie wewnętrznej konfiguracji domyślnej.")
        self._config = self._deep_copy_config(DEFAULT_CONFIG)
        self._resolve_paths_in_config_section(self._config.get('paths', {}), self.app_base_dir)
        self._resolve_cli_tool_paths(self._config.get('ffmpeg', {}))
        logger.debug(f"ConfigManager: Domyślna konfiguracja załadowana. id(self._config): {id(self._config)}")

    def _resolve_cli_tool_paths(self, tool_section_dict: Dict[str, Any]):
        if not tool_section_dict: return
        for key in ['ffmpeg_path', 'ffprobe_path', 'mkvmerge_path']:
            if key not in tool_section_dict: continue
            value = tool_section_dict.get(key)
            if isinstance(value, str):
                if not (Path(value).is_absolute() or value.startswith('~') or os.path.sep in value or (os.altsep and os.altsep in value)): tool_section_dict[key] = value 
                else: tool_section_dict[key] = Path(value).expanduser().resolve()
            elif isinstance(value, Path): tool_section_dict[key] = value.expanduser().resolve()

    def _resolve_paths_in_config_section(self, section_dict: Dict[str, Any], base_dir: Path):
        if not section_dict: return
        for key, value in section_dict.items():
            is_path_key = key.endswith(('_path', '_dir', '_file')) or \
                          key in ['last_used_source_directory', 'last_used_single_file_path', 'default_output_directory', 'default_repaired_directory', 'job_state_dir', 'repair_profiles_file', 'profiles_file', 'main_config_file']
            if is_path_key and isinstance(value, str):
                if not value: section_dict[key] = None; continue
                path_obj = Path(value)
                if value.startswith('~'): section_dict[key] = path_obj.expanduser().resolve()
                elif not path_obj.is_absolute(): section_dict[key] = (base_dir / path_obj).resolve()
                else: section_dict[key] = path_obj.resolve()
            elif is_path_key and isinstance(value, Path):
                if not value.is_absolute(): section_dict[key] = (base_dir / value).resolve()
                else: section_dict[key] = value.resolve()
    
    def load_config_from_file_and_merge(self):
        logger.debug(f"ConfigManager load_config_from_file_and_merge: id(self._config) na początku (powinno być z default): {id(self._config)}")
        if not self.config_file_path.exists():
            logger.warning(f"Plik konfiguracyjny nie znaleziony w {self.config_file_path}. Używanie wartości domyślnych. Plik zostanie utworzony przy pierwszym zapisie.")
            self.save_config(); return
        try:
            with open(self.config_file_path, 'r', encoding='utf-8') as f: loaded_config_from_file = yaml.safe_load(f)
            if loaded_config_from_file is None: logger.warning(f"Plik konfiguracyjny {self.config_file_path} jest pusty. Używanie wartości domyślnych (już załadowanych)."); return
            logger.debug(f"ConfigManager: Zawartość wczytana z {self.config_file_path} PRZED SCALENIEM:\n{json.dumps(loaded_config_from_file, indent=2, ensure_ascii=False)}")
            self._config = self._merge_configs(self._config, loaded_config_from_file) 
            logger.info(f"Pomyślnie załadowano i scalono konfigurację z {self.config_file_path}.")
            logger.debug(f"ConfigManager load_config_from_file_and_merge: id(self._config) po merge: {id(self._config)}")
            self._resolve_paths_in_config_section(self._config.get('paths', {}), self.app_base_dir)
            self._resolve_cli_tool_paths(self._config.get('ffmpeg', {}))
        except yaml.YAMLError as e: logger.error(f"Błąd parsowania pliku YAML {self.config_file_path}: {e}. Używanie konfiguracji domyślnej.", exc_info=True); self._backup_corrupted_config(self.config_file_path, "yaml_error")
        except Exception as e: logger.critical(f"Nieoczekiwany błąd ładowania konfiguracji z {self.config_file_path}: {e}.", exc_info=True); self._backup_corrupted_config(self.config_file_path, "load_error")

    def _backup_corrupted_config(self, file_to_backup: Path, suffix_reason: str):
        try:
            backup_path = file_to_backup.with_name(f"{file_to_backup.name}.backup_{suffix_reason}_{datetime.now():%Y%m%d%H%M%S}")
            if file_to_backup.exists(): shutil.copy2(file_to_backup, backup_path); logger.warning(f"Utworzono kopię zapasową uszkodzonego pliku konfiguracyjnego: {backup_path} z {file_to_backup}")
        except Exception as backup_e: logger.error(f"Nie udało się utworzyć kopii zapasowej {file_to_backup}: {backup_e}", exc_info=True)

    def _recursive_path_to_str(self, data: Any) -> Any:
        if isinstance(data, dict): return {k: self._recursive_path_to_str(v) for k, v in data.items()}
        elif isinstance(data, list): return [self._recursive_path_to_str(item) for item in data]
        elif isinstance(data, Path):
            is_tool_path_candidate = False; ffmpeg_section = self._config.get('ffmpeg', {})
            if isinstance(ffmpeg_section, dict):
                for tool_key_name in ffmpeg_section.keys():
                    if tool_key_name.endswith("_path") and str(data) == str(ffmpeg_section.get(tool_key_name)):
                        if not data.is_absolute(): return str(data)
                        is_tool_path_candidate = True; break 
            if not is_tool_path_candidate:
                try:
                    if str(data).startswith(str(Path.home())): return f"~/{data.relative_to(Path.home())}"
                    if self.app_base_dir in data.parents or self.app_base_dir == data: return str(data.relative_to(self.app_base_dir))
                except ValueError: pass
            return str(data)
        return data

    def _config_to_serializable(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        serializable_config = self._recursive_path_to_str(self._deep_copy_config(config_data)); return serializable_config

    def save_config(self, target_path: Optional[Path] = None):
        path_to_save = target_path if target_path else self.config_file_path; logger.debug(f"ConfigManager: Zapisywanie konfiguracji do {path_to_save}")
        try: path_to_save.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e: logger.error(f"ConfigManager: Nie można utworzyć katalogu {path_to_save.parent}: {e}", exc_info=True); return
        config_to_save_serializable = self._config_to_serializable(self._config)
        try:
            with open(path_to_save, 'w', encoding='utf-8') as f: yaml.dump(config_to_save_serializable, f, indent=4, sort_keys=False, Dumper=yaml.SafeDumper, default_flow_style=False, allow_unicode=True)
            logger.info(f"ConfigManager: Pomyślnie zapisano konfigurację do {path_to_save}.")
        except Exception as e: logger.error(f"ConfigManager: Błąd zapisu konfiguracji do {path_to_save}: {e}", exc_info=True)

    def _merge_configs(self, target: Dict[str, Any], source: Dict[str, Any], _path_debug: List[str] = None) -> Dict[str, Any]:
        if _path_debug is None: _path_debug = []
        for key, value_from_source in source.items():
            current_path_debug = _path_debug + [key]
            if key in target:
                if isinstance(value_from_source, dict) and isinstance(target[key], dict): self._merge_configs(target[key], value_from_source, current_path_debug)
                elif target[key] != value_from_source or type(target[key]) != type(value_from_source): 
                    logger.debug(f"MERGE ({'.'.join(current_path_debug)}): Nadpisywanie target '{repr(target[key])}' (typ: {type(target[key])}) -> source '{repr(value_from_source)}' (typ: {type(value_from_source)})")
                    target[key] = value_from_source
            else:
                logger.debug(f"MERGE ({'.'.join(current_path_debug)}): Dodawanie nowego klucza '{key}' z source: '{repr(value_from_source)}'")
                target[key] = value_from_source
        return target 

    def get_config(self) -> Dict[str, Any]: return self._deep_copy_config(self._config)

    def get_config_value(self, section_key: str, key: str, default: Any = None) -> Any:
        # POPRAWKA: Poprawne budowanie path_parts
        path_parts = []
        if section_key and section_key.strip():
            path_parts.extend(section_key.split('.'))
        
        # Jeśli 'key' samo w sobie może zawierać kropki (reprezentując zagnieżdżenie),
        # również je rozbijamy i dodajemy do path_parts.
        if key and key.strip():
            path_parts.extend(key.split('.')) 
        
        path_parts = [p for p in path_parts if p] # Usuń puste segmenty

        full_key_path_str = ".".join(path_parts)
        
        value_to_process: Any
        source_of_value: str = "unknown"

        val_from_config = _get_nested_value(self._config, path_parts, dict_name_for_log="self._config", default_return=_SENTINEL)
        if val_from_config is not _SENTINEL:
            value_to_process = val_from_config
            source_of_value = "self._config"
        else:
            val_from_default_config = _get_nested_value(DEFAULT_CONFIG, path_parts, dict_name_for_log="DEFAULT_CONFIG", default_return=_SENTINEL)
            if val_from_default_config is not _SENTINEL:
                value_to_process = val_from_default_config
                source_of_value = "DEFAULT_CONFIG"
            else: 
                value_to_process = default 
                source_of_value = "function_default_arg"
        
        # Zredukowano logowanie, aby nie zaśmiecać, ale można je włączyć dla konkretnych kluczy
        if logger.isEnabledFor(logging.DEBUG) or \
           full_key_path_str == 'processing.repair_options.builtin_strategies_config.mkvmerge_remux.enabled':
             logger.info(f"CM_GET_FINAL: Dla '{full_key_path_str}', źródło: {source_of_value}, wartość przed konwersją: {repr(value_to_process)} (Typ: {type(value_to_process)})")

        # Konwersja typów (bez zmian od #69)
        if full_key_path_str in ["general.log_level_file", "general.log_level_console"]:
            if isinstance(value_to_process, str): level_int = logging.getLevelName(value_to_process.upper()); return level_int if isinstance(level_int, int) else default 
            return value_to_process if isinstance(value_to_process, int) else default
        
        bool_keys_list = [
            "general.console_logging_enabled", "general.clear_log_on_start", "general.recursive_scan",
            "processing.delete_original_on_success", "processing.verify_repaired_files",
            "processing.auto_repair_on_suspicion", "ffmpeg.enable_dynamic_timeout",
            "processing.repair_options.attempt_sequentially",
            "processing.repair_options.use_custom_ffmpeg_repair_profiles",
            "processing.repair_options.builtin_strategies_config.mkvmerge_remux.enabled" 
        ]
        if full_key_path_str in bool_keys_list:
            if isinstance(value_to_process, bool): return value_to_process
            if isinstance(value_to_process, str): return value_to_process.lower() == 'true'
            # logger.warning(f"CM_GET (bool): Dla '{full_key_path_str}', wartość '{repr(value_to_process)}' nie jest bool/str. Zwracanie default: {default}")
            return default 

        numeric_keys_map = { "ffmpeg.dynamic_timeout_multiplier": float, "ffmpeg.dynamic_timeout_buffer_seconds": int, "ffmpeg.dynamic_timeout_min_seconds": int, "ffmpeg.fixed_timeout_seconds": int, "processing.repair_timeout_seconds": int, "ui.progress_bar_width": int, "ui.rich_monitor_refresh_rate": float, "ui.rich_monitor_disk_refresh_interval": float, "ui.legacy_monitor_refresh_interval": float, "ui.delay_between_files_seconds": float }
        if full_key_path_str in numeric_keys_map:
            expected_type = numeric_keys_map[full_key_path_str];
            if isinstance(value_to_process, expected_type): return value_to_process
            try:
                if isinstance(value_to_process, (str, int, float)): return expected_type(value_to_process)
            except ValueError: pass
            # logger.warning(f"CM_GET (numeric): Dla '{full_key_path_str}', wartość '{repr(value_to_process)}' nie mogła być '{expected_type.__name__}'. Zwracanie default: {default}"); 
            return default
        
        if len(path_parts) > 0 and path_parts[0] == 'ffmpeg' and path_parts[-1].endswith('_path'):
             if value_to_process is None: return None 
             if isinstance(value_to_process, Path): return value_to_process 
             if isinstance(value_to_process, str):
                 if not (Path(value_to_process).is_absolute() or value_to_process.startswith('~') or os.path.sep in value_to_process or (os.altsep and os.altsep in value_to_process)): return value_to_process 
                 return Path(value_to_process)
             return default

        is_general_path_key = (len(path_parts) > 0 and path_parts[0] == 'paths' and \
                              (any(s in path_parts[-1] for s in ['_path', '_dir', '_file']) or \
                               full_key_path_str in ['paths.last_used_source_directory', 'paths.default_output_directory', 
                                                    'paths.default_repaired_directory', 'paths.job_state_dir', 
                                                    'paths.repair_profiles_file', 'paths.profiles_file', 'paths.main_config_file']))
        if is_general_path_key:
            if value_to_process is None: return None
            if isinstance(value_to_process, Path): return value_to_process
            if isinstance(value_to_process, str): return Path(value_to_process)
            return default
            
        if full_key_path_str == "processing.repair_options.enabled_ffmpeg_profile_ids":
            return value_to_process if isinstance(value_to_process, list) else default if isinstance(default, list) else []
        if full_key_path_str == "processing.supported_file_extensions":
            return value_to_process if isinstance(value_to_process, list) else default if isinstance(default, list) else []

        return value_to_process

    def set_config_value(self, section_key: str, key: str, value: Any):
        # POPRAWKA: Budowanie path_parts
        path_parts = []
        if section_key and section_key.strip():
            path_parts.extend(section_key.split('.'))
        if key and key.strip(): # Jeśli key zawiera kropki, rozbij go również
            path_parts.extend(key.split('.'))
        else: # Jeśli key jest prosty lub pusty/None
            if key and key.strip(): path_parts.append(key)
        path_parts = [p for p in path_parts if p] # Usuń puste segmenty

        logger.debug(f"CM_SET: Próba ustawienia klucza: '{'.'.join(path_parts)}' na wartość: {repr(value)} (typ: {type(value)})")
        
        current_level_dict = self._config
        for i, k_part in enumerate(path_parts[:-1]):
            if k_part not in current_level_dict or not isinstance(current_level_dict[k_part], dict): 
                logger.debug(f"CM_SET: Tworzenie brakującego słownika dla klucza '{k_part}' na ścieżce '{'.'.join(path_parts[:i+1])}'")
                current_level_dict[k_part] = {}
            current_level_dict = current_level_dict[k_part]
        
        final_key_to_set = path_parts[-1]; full_key_path_str = ".".join(path_parts)
        value_to_store_final = value 
        
        # Logika typowania jak w #69
        is_log_level_key = full_key_path_str in ["general.log_level_file", "general.log_level_console"]
        is_tool_path = len(path_parts) > 0 and path_parts[0] == 'ffmpeg' and final_key_to_set.endswith('_path')
        is_general_path_config_key = (len(path_parts) > 0 and path_parts[0] == 'paths' and \
                                   (any(s in final_key_to_set for s in ['_path', '_dir', '_file']) or \
                                   final_key_to_set in ['last_used_source_directory', 'last_used_single_file_path', 'default_output_directory', 'default_repaired_directory', 'job_state_dir', 'repair_profiles_file', 'main_config_file', 'profiles_file']))
        bool_keys_list = ["general.console_logging_enabled", "general.clear_log_on_start", "general.recursive_scan", "processing.delete_original_on_success", "processing.verify_repaired_files", "processing.auto_repair_on_suspicion", "ffmpeg.enable_dynamic_timeout", "processing.repair_options.attempt_sequentially", "processing.repair_options.use_custom_ffmpeg_repair_profiles", "processing.repair_options.builtin_strategies_config.mkvmerge_remux.enabled"]
        is_bool_key = full_key_path_str in bool_keys_list
        numeric_keys_map = {"ffmpeg.dynamic_timeout_multiplier": float, "ffmpeg.dynamic_timeout_buffer_seconds": int, "ffmpeg.dynamic_timeout_min_seconds": int, "ffmpeg.fixed_timeout_seconds": int, "processing.repair_timeout_seconds": int, "ui.progress_bar_width": int, "ui.rich_monitor_refresh_rate": float, "ui.rich_monitor_disk_refresh_interval": float, "ui.legacy_monitor_refresh_interval": float, "ui.delay_between_files_seconds": float}
        is_numeric_key = full_key_path_str in numeric_keys_map
        if is_log_level_key:
            if isinstance(value, int):
                lvl_name = logging.getLevelName(value)
                if lvl_name.startswith("Level "): logger.error(f"Zły int dla log level '{value}' dla '{full_key_path_str}'."); return
                value_to_store_final = lvl_name 
            elif isinstance(value, str) and value.upper() in logging._nameToLevel: value_to_store_final = value.upper()
            else: logger.error(f"Zły typ/wartość dla log level '{value}' dla '{full_key_path_str}'."); return
        elif is_bool_key: value_to_store_final = bool(value)
        elif is_numeric_key:
            expected_type = numeric_keys_map[full_key_path_str]
            try: value_to_store_final = expected_type(value)
            except (ValueError, TypeError): logger.error(f"Zła wartość numeryczna '{value}' dla '{full_key_path_str}'. Oczekiwano {expected_type.__name__}."); return
        elif is_tool_path:
            if value is None or (isinstance(value, str) and not value.strip()):
                default_tool_val = DEFAULT_CONFIG.get(path_parts[0],{}).get(final_key_to_set)
                value_to_store_final = default_tool_val 
            elif isinstance(value, (str, Path)):
                path_obj = Path(value) if isinstance(value, str) else value
                if not (path_obj.is_absolute() or str(value).startswith('~') or os.path.sep in str(value) or (os.altsep and os.altsep in str(value))): value_to_store_final = str(value)
                else: value_to_store_final = path_obj.expanduser().resolve()
            else: logger.error(f"Zły typ '{type(value)}' dla ścieżki narzędzia '{full_key_path_str}'."); return
        elif is_general_path_config_key: 
            if value is None or (isinstance(value, str) and not value.strip()): value_to_store_final = None
            elif isinstance(value, (str, Path)): 
                path_obj = Path(value) if isinstance(value, str) else value
                if str(value).startswith('~'): value_to_store_final = path_obj.expanduser().resolve()
                elif not path_obj.is_absolute(): value_to_store_final = (self.app_base_dir / path_obj).resolve()
                else: value_to_store_final = path_obj.resolve()
            else: logger.error(f"Zły typ '{type(value)}' dla ścieżki '{full_key_path_str}'."); return
        elif full_key_path_str == "processing.repair_options.enabled_ffmpeg_profile_ids":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                logger.error(f"Nieprawidłowa wartość dla 'enabled_ffmpeg_profile_ids', oczekiwano listy stringów: {value}"); return
            value_to_store_final = value
        
        current_level_dict[final_key_to_set] = value_to_store_final
        logger.info(f"ConfigManager: Wartość dla '{full_key_path_str}' zaktualizowana na '{repr(value_to_store_final)}' (typ w pamięci: {type(value_to_store_final)}).")
        self.save_config()

    def get_log_file_full_path(self) -> Path:
        log_file_setting = self.get_config_value('paths', 'log_file');
        if log_file_setting is None: log_file_setting = DEFAULT_CONFIG['paths']['log_file']
        log_file_path = Path(log_file_setting) if not isinstance(log_file_setting, Path) else log_file_setting
        if log_file_path.is_absolute(): return log_file_path.resolve()
        return (self.app_base_dir / log_file_path).resolve()

    def get_profiles_file_full_path(self) -> Path:
        profiles_file_setting = self.get_config_value('paths', 'profiles_file')
        if profiles_file_setting is None: profiles_file_setting = DEFAULT_CONFIG['paths']['profiles_file']
        profiles_file_path = Path(profiles_file_setting) if not isinstance(profiles_file_setting, Path) else profiles_file_setting
        if profiles_file_path.is_absolute(): return profiles_file_path.resolve()
        return (self.app_base_dir / profiles_file_path).resolve()

    def get_repair_profiles_file_full_path(self) -> Path:
        repair_profiles_file_setting = self.get_config_value('paths', 'repair_profiles_file')
        if repair_profiles_file_setting is None: 
            repair_profiles_file_setting = DEFAULT_CONFIG['paths']['repair_profiles_file']
        repair_profiles_file_path = Path(repair_profiles_file_setting) if not isinstance(repair_profiles_file_setting, Path) else repair_profiles_file_setting
        if repair_profiles_file_path.is_absolute(): 
            return repair_profiles_file_path.resolve()
        return (self.app_base_dir / repair_profiles_file_path).resolve()

    def get_job_state_dir_full_path(self) -> Path:
        path_val = self.get_config_value('paths', 'job_state_dir')
        if path_val is None: path_val = DEFAULT_CONFIG['paths']['job_state_dir']
        path_obj = Path(path_val) if not isinstance(path_val, Path) else path_val
        if str(path_val).startswith("~") or path_obj.is_absolute() :
             return path_obj.expanduser().resolve()
        return (self.app_base_dir / path_obj).resolve()

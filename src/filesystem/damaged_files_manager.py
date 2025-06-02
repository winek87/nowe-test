# src/filesystem/damaged_files_manager.py
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..models import AppJSONEncoder, AppJSONDecoder, MediaInfo
from ..config_manager import ConfigManager
from ..ffmpeg.ffmpeg_manager import FFmpegManager

logger = logging.getLogger(__name__)

class DamagedFilesManager:
    """
    Zarządza listą plików zidentyfikowanych jako potencjalnie uszkodzone.
    Zapisuje i wczytuje tę listę z pliku JSON.
    """
    def __init__(self, config_manager: ConfigManager, ffmpeg_manager: FFmpegManager):
        self.config_manager = config_manager
        self.ffmpeg_manager = ffmpeg_manager
        self.job_state_dir: Path = self.config_manager.get_job_state_dir_full_path()
        self.damaged_files_list_file: Path = self.job_state_dir / "damaged_files_registry.json"
        
        logger.debug(f"DamagedFilesManager zainicjalizowany. Plik listy uszkodzonych plików: {self.damaged_files_list_file}")
        try:
            self.job_state_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.critical(f"Nie można utworzyć katalogu stanu zadań {self.job_state_dir} dla DamagedFilesManager: {e}", exc_info=True)

    def _load_damaged_files_list(self) -> List[Dict[str, Any]]:
        """Wczytuje listę uszkodzonych plików z pliku JSON."""
        if not self.damaged_files_list_file.exists():
            logger.info("Nie znaleziono pliku listy uszkodzonych plików. Zwracanie pustej listy.")
            return []
        try:
            with open(self.damaged_files_list_file, 'r', encoding='utf-8') as f:
                damaged_list = json.load(f, cls=AppJSONDecoder)
            if not isinstance(damaged_list, list):
                logger.error(f"Zawartość pliku uszkodzonych plików nie jest listą ({type(damaged_list)}). Zwracanie pustej listy.")
                self._backup_corrupted_file("not_a_list")
                return []
            
            valid_entries = []
            for entry in damaged_list:
                if isinstance(entry, dict) and 'file_path' in entry:
                    if isinstance(entry['file_path'], str):
                        entry['file_path'] = Path(entry['file_path'])
                    valid_entries.append(entry)
                else:
                    logger.warning(f"Pominięto nieprawidłowy wpis na liście uszkodzonych plików: {entry}")
            
            logger.info(f"Pomyślnie wczytano {len(valid_entries)} wpisów z listy uszkodzonych plików.")
            return valid_entries
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Błąd podczas wczytywania lub parsowania listy uszkodzonych plików z {self.damaged_files_list_file}: {e}", exc_info=True)
            self._backup_corrupted_file("load_error")
            return []
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas wczytywania listy uszkodzonych plików: {e}", exc_info=True)
            self._backup_corrupted_file("unexpected_error")
            return []

    def _save_damaged_files_list(self, damaged_files_list: List[Dict[str, Any]]):
        """Zapisuje listę uszkodzonych plików do pliku JSON."""
        logger.debug(f"Zapisywanie {len(damaged_files_list)} wpisów do listy uszkodzonych plików: {self.damaged_files_list_file}")
        try:
            with open(self.damaged_files_list_file, 'w', encoding='utf-8') as f:
                json.dump(damaged_files_list, f, indent=4, cls=AppJSONEncoder)
            logger.info(f"Pomyślnie zapisano listę uszkodzonych plików ({len(damaged_files_list)} wpisów).")
        except Exception as e:
            logger.error(f"Błąd podczas zapisu listy uszkodzonych plików: {e}", exc_info=True)

    def _backup_corrupted_file(self, suffix_reason: str):
        """Tworzy kopię zapasową uszkodzonego pliku listy uszkodzonych plików."""
        try:
            backup_path = self.damaged_files_list_file.with_name(
                f"{self.damaged_files_list_file.name}.backup_{suffix_reason}_{datetime.now():%Y%m%d%H%M%S}"
            )
            if self.damaged_files_list_file.exists():
                self.damaged_files_list_file.rename(backup_path)
                logger.warning(f"Utworzono kopię zapasową uszkodzonego pliku listy uszkodzonych plików: {backup_path}")
        except Exception as backup_e:
            logger.error(f"Nie udało się utworzyć kopii zapasowej uszkodzonego pliku listy uszkodzonych plików {self.damaged_files_list_file}: {backup_e}", exc_info=True)

    def add_damaged_file(self, file_path: Path, error_details: str, media_info: Optional[MediaInfo] = None):
        logger.info(f"Próba dodania pliku '{file_path.name}' do listy uszkodzonych. Powód: {error_details[:100]}...")
        damaged_files = self._load_damaged_files_list()
        resolved_file_path = file_path.resolve()
        for entry in damaged_files:
            entry_path = entry.get('file_path')
            if isinstance(entry_path, Path) and entry_path.resolve() == resolved_file_path:
                logger.info(f"Plik '{file_path.name}' jest już na liście uszkodzonych. Aktualizacja informacji.")
                entry['timestamp'] = datetime.now()
                entry['error_details'] = error_details
                if media_info:
                    entry['media_info'] = media_info.to_dict()
                self._save_damaged_files_list(damaged_files)
                return

        new_entry: Dict[str, Any] = {
            'file_path': file_path,
            'timestamp': datetime.now(),
            'error_details': error_details,
            'status': 'Reported'
        }
        if media_info:
            new_entry['media_info'] = media_info.to_dict()

        damaged_files.append(new_entry)
        self._save_damaged_files_list(damaged_files)
        logger.info(f"Dodano plik '{file_path.name}' do listy uszkodzonych.")

    def remove_damaged_file(self, file_path: Path) -> bool:
        logger.info(f"Próba usunięcia pliku '{file_path.name}' z listy uszkodzonych.")
        damaged_files = self._load_damaged_files_list()
        initial_count = len(damaged_files)
        resolved_file_path = file_path.resolve()
        filtered_list = [
            entry for entry in damaged_files
            if not (isinstance(entry.get('file_path'), Path) and entry['file_path'].resolve() == resolved_file_path)
        ]
        if len(filtered_list) < initial_count:
            self._save_damaged_files_list(filtered_list)
            logger.info(f"Pomyślnie usunięto plik '{file_path.name}' z listy uszkodzonych.")
            return True
        else:
            logger.warning(f"Plik '{file_path.name}' nie został znaleziony na liście uszkodzonych.")
            return False

    def get_damaged_files(self) -> List[Dict[str, Any]]:
        """Zwraca listę wszystkich zarejestrowanych uszkodzonych plików."""
        return self._load_damaged_files_list()

    def update_damaged_file_status(self, file_path: Path, new_status: str, new_error_details: Optional[str] = None) -> bool:
        damaged_files = self._load_damaged_files_list()
        updated = False
        resolved_file_path = file_path.resolve()
        for entry in damaged_files:
            entry_path = entry.get('file_path')
            if isinstance(entry_path, Path) and entry_path.resolve() == resolved_file_path:
                entry['status'] = new_status
                entry['timestamp'] = datetime.now()
                if new_error_details is not None:
                    entry['error_details'] = new_error_details
                updated = True
                break
        if updated:
            self._save_damaged_files_list(damaged_files)
            logger.info(f"Zaktualizowano status pliku '{file_path.name}' na liście uszkodzonych na '{new_status}'.")
        else:
            logger.warning(f"Nie znaleziono pliku '{file_path.name}' na liście uszkodzonych do aktualizacji statusu.")
        return updated

    def verify_files_on_list(self) -> List[Dict[str, Any]]:
        logger.info("Rozpoczynanie weryfikacji plików z listy uszkodzonych...")
        damaged_files = self._load_damaged_files_list()
        files_to_keep = []
        files_removed_count = 0
        for entry in damaged_files:
            file_path = entry.get('file_path')
            if not isinstance(file_path, Path):
                logger.warning(f"Pominięto wpis z nieprawidłową ścieżką podczas weryfikacji: {entry}")
                files_to_keep.append(entry)
                continue
            logger.debug(f"Weryfikacja pliku: {file_path.name}")
            if self.ffmpeg_manager.is_file_readable_by_ffprobe(file_path):
                logger.info(f"Plik '{file_path.name}' z listy uszkodzonych jest teraz czytelny. Usuwanie z listy.")
                files_removed_count += 1
            else:
                logger.info(f"Plik '{file_path.name}' nadal nie jest czytelny. Pozostawianie na liście.")
                files_to_keep.append(entry)
        if files_removed_count > 0:
            self._save_damaged_files_list(files_to_keep)
            logger.info(f"Zakończono weryfikację. Usunięto {files_removed_count} plików z listy uszkodzonych.")
        else:
            logger.info("Zakończono weryfikację. Żaden plik nie został usunięty z listy uszkodzonych.")
        return files_to_keep

    def clear_all_damaged_files(self):
        """Usuwa wszystkie wpisy z listy uszkodzonych plików."""
        logger.info("Czyszczenie całej listy uszkodzonych plików.")
        self._save_damaged_files_list([]) # Zapisz pustą listę
        logger.info("Lista uszkodzonych plików została wyczyszczona.")

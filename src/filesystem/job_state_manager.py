# src/filesystem/job_state_manager.py
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List # <<< DODANO IMPORT List
from datetime import datetime

from ..models import JobState, ProcessedFile, AppJSONEncoder, AppJSONDecoder # Import modeli i (de)serializatorów
from ..config_manager import ConfigManager # Dla dostępu do ścieżki job_state_dir

logger = logging.getLogger(__name__)

class JobStateManager:
    """
    Zarządza zapisywaniem i wczytywaniem stanu zadań transkodowania.
    Obecnie zadanie dotyczy jednego pliku, ale struktura JobState jest zachowana.
    """
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        # job_state_dir jest głównym katalogiem dla danych aplikacji
        self.job_state_dir: Path = self.config_manager.get_job_state_dir_full_path()
        
        # Plik przechowujący stan ostatniego zadania
        self.last_job_state_file: Path = self.job_state_dir / "last_single_job_state.json"
        
        logger.debug(f"JobStateManager zainicjalizowany. Plik stanu ostatniego zadania: {self.last_job_state_file}")
        # Upewnij się, że katalog istnieje
        try:
            self.job_state_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.critical(f"Nie można utworzyć katalogu stanu zadań {self.job_state_dir}: {e}", exc_info=True)
            # To może być krytyczny błąd, w zależności od wymagań aplikacji

    def save_job_state(self, job_state: JobState):
        """Zapisuje bieżący stan zadania do pliku JSON."""
        logger.info(f"Zapisywanie stanu zadania {job_state.job_id} do {self.last_job_state_file}")
        try:
            with open(self.last_job_state_file, 'w', encoding='utf-8') as f:
                json.dump(job_state, f, indent=4, cls=AppJSONEncoder) # Użyj niestandardowego enkodera
            logger.info(f"Pomyślnie zapisano stan zadania {job_state.job_id}.")
        except Exception as e:
            logger.error(f"Błąd podczas zapisu stanu zadania {job_state.job_id}: {e}", exc_info=True)
            # Można rozważyć rzucenie wyjątku w zależności od krytyczności

    def load_last_job_state(self) -> Optional[JobState]:
        """Wczytuje ostatni zapisany stan zadania z pliku JSON."""
        logger.debug(f"Próba wczytania stanu ostatniego zadania z {self.last_job_state_file}")
        if not self.last_job_state_file.exists():
            logger.info("Nie znaleziono pliku stanu ostatniego zadania.")
            return None

        try:
            with open(self.last_job_state_file, 'r', encoding='utf-8') as f:
                # Użyj niestandardowego dekodera do obsługi Path, datetime i UUID
                job_state_data = json.load(f, cls=AppJSONDecoder)
            
            if isinstance(job_state_data, JobState): # Jeśli AppJSONDecoder już przekonwertował
                 job_state = job_state_data
            elif isinstance(job_state_data, dict): # Jeśli to słownik, spróbuj przekonwertować
                 job_state = JobState.from_dict(job_state_data)
            else:
                 logger.error(f"Nieoczekiwany typ danych wczytany z pliku stanu zadania: {type(job_state_data)}")
                 self._backup_corrupted_job_state_file("invalid_type")
                 return None

            logger.info(f"Pomyślnie wczytano stan zadania {job_state.job_id}.")
            return job_state

        except (json.JSONDecodeError, ValueError) as e: # ValueError z from_dict
            logger.error(f"Błąd podczas wczytywania lub parsowania stanu zadania z {self.last_job_state_file}: {e}", exc_info=True)
            self._backup_corrupted_job_state_file("load_error")
            return None
        except Exception as e: # Inne nieoczekiwane błędy
            logger.error(f"Nieoczekiwany błąd podczas wczytywania stanu zadania: {e}", exc_info=True)
            self._backup_corrupted_job_state_file("unexpected_error")
            return None
            
    def _backup_corrupted_job_state_file(self, suffix_reason: str):
        """Tworzy kopię zapasową uszkodzonego pliku stanu zadania."""
        try:
            backup_path = self.last_job_state_file.with_name(
                f"{self.last_job_state_file.name}.backup_{suffix_reason}_{datetime.now():%Y%m%d%H%M%S}"
            )
            if self.last_job_state_file.exists():
                self.last_job_state_file.rename(backup_path)
                logger.warning(f"Utworzono kopię zapasową uszkodzonego pliku stanu zadania: {backup_path}")
        except Exception as backup_e:
            logger.error(f"Nie udało się utworzyć kopii zapasowej uszkodzonego pliku stanu zadania {self.last_job_state_file}: {backup_e}", exc_info=True)

    def get_history_of_jobs(self, limit: int = 10) -> List[JobState]:
        """
        (Przyszłościowa funkcja) Wczytuje historię zadań.
        Wymagałoby to zmiany sposobu zapisywania stanu zadań (np. każdy job w osobnym pliku
        lub lista jobów w jednym pliku). Na razie niezaimplementowane.
        """
        logger.warning("Funkcja get_history_of_jobs nie jest jeszcze zaimplementowana.")
        return []

    def clear_job_history(self):
        """
        (Przyszłościowa funkcja) Czyści historię zadań.
        """
        logger.warning("Funkcja clear_job_history nie jest jeszcze zaimplementowana.")
        # Potencjalnie usuwa plik last_job_state_file lub inne pliki historii
        # if self.last_job_state_file.exists():
        #     try:
        #         self.last_job_state_file.unlink()
        #         logger.info(f"Usunięto plik stanu ostatniego zadania: {self.last_job_state_file}")
        #     except OSError as e:
        #         logger.error(f"Nie można usunąć pliku stanu ostatniego zadania {self.last_job_state_file}: {e}")
        pass

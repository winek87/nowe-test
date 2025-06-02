# src/filesystem/directory_scanner.py
import logging
import os
from pathlib import Path
from typing import List, Optional, Callable, Tuple 
import uuid 

from ..models import ProcessedFile, MediaInfo, JobState 
from ..ffmpeg.ffmpeg_manager import FFmpegManager 
from ..config_manager import ConfigManager 
from ..filesystem.path_resolver import PathResolver # <-- DODANO
from ..filesystem.damaged_files_manager import DamagedFilesManager # <-- DODANO

logger = logging.getLogger(__name__)

ScanProgressCallback = Callable[[int, int, str], None] 

class DirectoryScanner:
    def __init__(self, 
                 config_manager: ConfigManager, 
                 ffmpeg_manager: FFmpegManager,
                 path_resolver: PathResolver,             # <-- DODANO
                 damaged_files_manager: DamagedFilesManager # <-- DODANO
                ):
        self.config_manager = config_manager
        self.ffmpeg_manager = ffmpeg_manager
        self.path_resolver = path_resolver                # <-- DODANO
        self.damaged_files_manager = damaged_files_manager  # <-- DODANO
        logger.debug("DirectoryScanner zainicjalizowany.")

    def _try_auto_repair(self, original_file_path: Path, original_media_info: MediaInfo) -> Optional[MediaInfo]:
        """
        Prywatna metoda do próby automatycznej naprawy pliku.
        Zwraca MediaInfo naprawionego pliku, jeśli się udało, w przeciwnym razie None.
        """
        logger.info(f"Automatyczna próba naprawy pliku: '{original_file_path.name}' (problem: {original_media_info.error_message})")
        
        # Użyj PathResolver do uzyskania ścieżki dla naprawionego pliku
        # Katalog dla naprawionych plików z konfiguracji
        repaired_dir_str = self.config_manager.get_config_value('paths', 'default_repaired_directory')
        repaired_dir = Path(repaired_dir_str).expanduser().resolve() if repaired_dir_str else self.path_resolver.app_base_dir / "repaired_default" # Fallback
        
        # Generuj nazwę dla naprawionego pliku, np. z przyrostkiem _repaired
        # PathResolver.generate_unique_output_path może być tu przydatny, aby uniknąć nadpisywania
        # ale najpierw potrzebujemy "bazowej" nazwy dla naprawionego pliku.
        # Możemy użyć oryginalnej nazwy w katalogu 'repaired'.
        tentative_repaired_path = repaired_dir / original_file_path.name
        
        # Użyj PathResolver do wygenerowania unikalnej ścieżki, jeśli plik już istnieje
        # (np. z poprzedniej próby naprawy)
        # is_repair_path=True w generate_unique_output_path dodało by _repaired, ale my już jesteśmy w katalogu repaired.
        # Dla uproszczenia, na razie użyjemy generate_unique_output_path bez specjalnego traktowania jako ścieżki naprawy.
        # Chcemy, aby plik miał taką samą nazwę, ale w innym folderze, a jeśli już jest - dodaj licznik.
        final_repaired_path = self.path_resolver.generate_unique_output_path(tentative_repaired_path, is_repair_path=False)
        
        logger.info(f"Docelowa ścieżka dla naprawionego pliku: {final_repaired_path}")

        # Użyj metody z FFmpegManager, która wykonuje prostą naprawę (np. ffmpeg -c copy)
        # Obecnie jest to FFmpegManager.attempt_repair_file()
        repair_success, repair_error_msg = self.ffmpeg_manager.attempt_repair_file(original_file_path, final_repaired_path)

        if repair_success:
            logger.info(f"Automatyczna naprawa pliku '{original_file_path.name}' powiodła się. Nowy plik: '{final_repaired_path.name}'")
            # Zarejestruj oryginalny plik jako uszkodzony, ale z adnotacją o udanej naprawie
            self.damaged_files_manager.add_damaged_file(
                original_file_path, 
                f"Oryginał uszkodzony ({original_media_info.error_message}), ale pomyślnie naprawiony do: {final_repaired_path.name}",
                original_media_info, # Przekaż oryginalne MediaInfo
                status="Repaired_OK"
            )
            # Pobierz MediaInfo dla nowego, naprawionego pliku
            repaired_media_info = self.ffmpeg_manager.get_media_info(final_repaired_path)
            if repaired_media_info.error_message or (repaired_media_info.duration is None or repaired_media_info.duration <= 0):
                logger.warning(f"Naprawiony plik '{final_repaired_path.name}' nadal ma problemy z metadanymi: {repaired_media_info.error_message or 'brak czasu trwania'}")
                # Można zdecydować, czy w takim przypadku używać naprawionego pliku, czy zgłosić błąd
                # Na razie zwracamy MediaInfo naprawionego pliku, nawet jeśli ma drobne problemy.
                repaired_media_info.error_message = f"Naprawiony, ale nadal problematyczny: {repaired_media_info.error_message or 'brak czasu trwania'}"
                self.damaged_files_manager.update_damaged_file_status(original_file_path, "Repaired_With_Issues", repaired_media_info.error_message)
                return repaired_media_info # Zwróć, aby dalej przetwarzać naprawiony plik
            else:
                 return repaired_media_info # Zwróć MediaInfo dla naprawionego pliku
        else:
            logger.warning(f"Automatyczna naprawa pliku '{original_file_path.name}' nie powiodła się. Błąd: {repair_error_msg}")
            self.damaged_files_manager.add_damaged_file(original_file_path, original_media_info.error_message or "Błąd odczytu", original_media_info, status=f"AutoRepair_Failed ({repair_error_msg})")
            return None # Naprawa nieudana, zwracamy None


    def scan_single_file(self, file_path: Path) -> Optional[MediaInfo]:
        logger.info(f"Skanowanie pojedynczego pliku: {file_path}")
        if not file_path.is_file():
            logger.error(f"Podana ścieżka nie jest plikiem: {file_path}")
            return MediaInfo(file_path=file_path, error_message=f"Ścieżka nie jest plikiem: {file_path}")

        # Sprawdzenie rozszerzenia - pozostaje bez zmian
        supported_extensions = self.config_manager.get_config_value('processing', 'supported_file_extensions', [])
        if supported_extensions and file_path.suffix.lower() not in [ext.lower() for ext in supported_extensions]:
            logger.debug(f"Plik '{file_path.name}' ma nieobsługiwane rozszerzenie '{file_path.suffix}'. Pomijanie.")
            return None # Zwracamy None, jeśli rozszerzenie nie jest obsługiwane - JobHandler to pominie

        # Krok 1: Pobierz MediaInfo dla oryginalnego pliku
        original_media_info = self.ffmpeg_manager.get_media_info(file_path) 

        # Krok 2: Sprawdź, czy plik jest problematyczny
        is_problematic = False
        if original_media_info.error_message:
            logger.warning(f"Plik '{file_path.name}' zgłosił błąd podczas odczytu MediaInfo: {original_media_info.error_message}")
            is_problematic = True
        elif original_media_info.duration is None or original_media_info.duration <= 0:
            logger.warning(f"Plik '{file_path.name}' ma nieprawidłowy lub zerowy czas trwania ({original_media_info.duration}s).")
            original_media_info.error_message = original_media_info.error_message or "Plik ma nieprawidłowy lub zerowy czas trwania."
            is_problematic = True
        
        # Krok 3: Jeśli problematyczny, spróbuj automatycznej naprawy (jeśli włączona)
        if is_problematic:
            auto_repair_enabled = self.config_manager.get_config_value('processing', 'auto_repair_on_suspicion', False)
            if auto_repair_enabled:
                repaired_media_info = self._try_auto_repair(file_path, original_media_info)
                if repaired_media_info:
                    logger.info(f"Automatyczna naprawa dla '{file_path.name}' zakończona. Używanie naprawionego pliku: '{repaired_media_info.file_path.name}'")
                    return repaired_media_info # Zwróć MediaInfo dla naprawionego pliku
                else:
                    logger.warning(f"Automatyczna naprawa dla '{file_path.name}' nie powiodła się. Używanie oryginalnego pliku z błędem.")
                    # Oryginalny plik został już dodany do damaged_files_manager w _try_auto_repair
                    return original_media_info # Zwróć oryginalne MediaInfo z błędem
            else: # Auto-naprawa wyłączona
                logger.info(f"Automatyczna naprawa jest wyłączona. Dodawanie '{file_path.name}' do listy uszkodzonych.")
                self.damaged_files_manager.add_damaged_file(file_path, original_media_info.error_message or "Problem z MediaInfo.", original_media_info)
                return original_media_info # Zwróć oryginalne MediaInfo z błędem
        
        # Krok 4: Jeśli plik nie był problematyczny (lub auto-naprawa była wyłączona)
        logger.debug(f"Skanowanie pliku '{file_path.name}' zakończone. Brak bezpośrednich problemów lub auto-naprawa wyłączona.")
        return original_media_info


    def scan_directory_for_media_files(
            self,
            source_directory: Path,
            recursive: bool,
            file_extensions: Optional[List[str]],
            progress_callback: Optional[ScanProgressCallback] = None
        ) -> List[MediaInfo]:
        logger.info(f"Rozpoczynanie skanowania katalogu '{source_directory}'. Rekursywnie: {recursive}")
        found_media_infos: List[MediaInfo] = []

        if not source_directory.is_dir():
            logger.error(f"Podana ścieżka źródłowa nie jest katalogiem: {source_directory}")
            return found_media_infos 

        normalized_extensions = [ext.lower() for ext in file_extensions] if file_extensions else None
        
        potential_files: List[Path] = []
        if recursive:
            for root, _, files in os.walk(source_directory):
                for filename in files: potential_files.append(Path(root) / filename)
        else:
            for item in source_directory.iterdir():
                if item.is_file(): potential_files.append(item)
        
        files_to_analyze: List[Path] = []
        if normalized_extensions:
            for pf_path in potential_files:
                if pf_path.suffix.lower() in normalized_extensions: files_to_analyze.append(pf_path)
        else: files_to_analyze = potential_files
        
        total_to_analyze = len(files_to_analyze)
        logger.info(f"Znaleziono {total_to_analyze} plików pasujących do kryteriów rozszerzeń do analizy.")
        if progress_callback and total_to_analyze == 0: progress_callback(0, 0, "Brak plików do analizy")

        for idx, file_path in enumerate(files_to_analyze):
            if progress_callback: progress_callback(idx + 1, total_to_analyze, file_path.name)
            
            media_info = self.scan_single_file(file_path) # scan_single_file teraz obsługuje logikę auto-naprawy
            if media_info: # scan_single_file zwróci MediaInfo (oryginalne lub naprawione) lub None jeśli np. złe rozszerzenie
                found_media_infos.append(media_info)
            # Jeśli scan_single_file zwróciło None (np. z powodu nieobsługiwanego rozszerzenia), po prostu pomijamy

        logger.info(f"Skanowanie MediaInfo zakończone. Przeanalizowano/próbowano naprawić {len(files_to_analyze)} plików. Zebrano {len(found_media_infos)} obiektów MediaInfo.")
        return found_media_infos


    def scan_directory_and_populate_job_state(self, job_state: JobState, progress_callback: Optional[ScanProgressCallback] = None):
        source_dir = job_state.source_directory
        recursive = self.config_manager.get_config_value('general', 'recursive_scan', False)
        file_extensions = self.config_manager.get_config_value('processing', 'supported_file_extensions', [])
        
        logger.info(f"Wypełnianie JobState dla zadania {job_state.job_id} z katalogu '{source_dir}'.")
        
        job_state.processed_files = []
        job_state.total_files = 0
        
        if not source_dir.is_dir():
            job_state.status = "Błąd skanowania"
            job_state.error_message = f"Katalog źródłowy '{source_dir}' nie istnieje lub nie jest katalogiem."
            logger.error(job_state.error_message)
            return

        all_media_infos = self.scan_directory_for_media_files(
            source_directory=source_dir,
            recursive=recursive,
            file_extensions=file_extensions,
            progress_callback=progress_callback
        )
        
        for media_info in all_media_infos:
            # media_info.file_path będzie teraz wskazywać na oryginalny lub naprawiony plik
            pf_status = "Oczekuje"
            if media_info.error_message: # Jeśli nadal jest błąd (nawet po próbie naprawy)
                pf_status = "Błąd odczytu" # lub inny odpowiedni status

            processed_file = ProcessedFile(
                file_id=uuid.uuid4(),
                original_path=media_info.file_path, # To jest teraz kluczowe - może to być ścieżka do naprawionego pliku
                status=pf_status,
                media_info=media_info, 
                duration_seconds=media_info.duration if media_info.duration is not None else 0.0,
                error_message=media_info.error_message # Zapisz komunikat błędu, jeśli nadal istnieje
            )
            job_state.processed_files.append(processed_file)
        
        job_state.total_files = len(job_state.processed_files)
        if job_state.total_files > 0:
            # Sprawdź, czy wszystkie pliki mają błąd, aby odpowiednio ustawić status zadania
            if all(pf.status.startswith("Błąd") for pf in job_state.processed_files):
                job_state.status = "Błąd (wszystkie pliki)"
            else:
                job_state.status = "Gotowe do przetworzenia"
        else:
            job_state.status = "Zakończono (brak plików)"
            logger.info(f"Nie dodano żadnych plików do zadania '{job_state.job_id}' z katalogu '{source_dir}'.")

        logger.info(f"Zakończono wypełnianie JobState dla zadania '{job_state.job_id}'. Dodano {job_state.total_files} plików.")

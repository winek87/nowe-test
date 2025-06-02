# src/profiler.py
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import uuid # Import uuid do generowania ID profili
import sys # Dla sys.exit przy krytycznych błędach

# Import ConfigManager do dostępu do konfiguracji
from .config_manager import ConfigManager
# Import modeli do wskazówek typów i (de)serializacji
from .models import EncodingProfile, AppJSONEncoder, AppJSONDecoder # Import niestandardowego enkodera/dekodera

logger = logging.getLogger(__name__)

class Profiler:
    """
    Zarządza profilami kodowania, włącznie z ładowaniem z i zapisywaniem do pliku JSON.
    Dostarcza metody do dodawania, aktualizowania, usuwania i pobierania profili.
    """
    def __init__(self, config_manager: ConfigManager):
        logger.debug("Profiler: Inicjalizacja rozpoczęta.")
        self.config_manager = config_manager # Przechowaj instancję ConfigManager

        # Pobierz ścieżkę do pliku profili z konfiguracji
        # Użyj metody pomocniczej z ConfigManager, aby uzyskać pełną, rozwiązaną ścieżkę
        self.profiles_file_path: Path = self.config_manager.get_profiles_file_full_path()
        logger.info(f"Profiler: Używany plik profili: {self.profiles_file_path}")

        # Upewnij się, że katalog nadrzędny dla pliku profili istnieje
        try:
            self.profiles_file_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Profiler: Upewniono się, że katalog profili istnieje: {self.profiles_file_path.parent}")
        except OSError as e:
            logger.critical(f"Profiler: BŁĄD KRYTYCZNY: Nie można utworzyć katalogu profili {self.profiles_file_path.parent}: {e}", exc_info=True)
            sys.exit(1) # Wyjdź z aplikacji, jeśli katalog nie może być utworzony

        self.profiles: List[EncodingProfile] = self._load_profiles()
        if not self.profiles:
            logger.info("Profiler: Nie załadowano żadnych profili. Rozważ utworzenie domyślnego profilu.")
            # Można tutaj dodać logikę tworzenia domyślnego profilu, jeśli plik jest pusty lub go nie ma.
            # self._create_default_profile_if_empty()
        else:
            logger.info(f"Profiler: Zainicjalizowano z {len(self.profiles)} profilami z {self.profiles_file_path}.")
        logger.debug("Profiler: Inicjalizacja zakończona.")

    def _create_default_profile_if_empty(self):
        """Tworzy domyślny profil, jeśli lista profili jest pusta."""
        if not self.profiles:
            default_profile = EncodingProfile(
                id=uuid.uuid4(),
                name="Domyślny H.264 AAC",
                description="Standardowy profil H.264 z dźwiękiem AAC, dobra kompatybilność.",
                ffmpeg_params=[
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
                    '-c:a', 'aac', '-b:a', '128k',
                    '-movflags', '+faststart' # Dla streamingu webowego
                ],
                output_extension='mp4',
                output_settings={'subdirectory': 'default_h264'}
            )
            try:
                self.add_profile(default_profile, save=True) # Dodaj i od razu zapisz
                logger.info(f"Profiler: Utworzono i zapisano domyślny profil: {default_profile.name}")
            except ValueError as e: # Jeśli add_profile zgłosi błąd (np. duplikat, choć nie powinien tu wystąpić)
                logger.error(f"Profiler: Nie udało się dodać domyślnego profilu: {e}")


    def _load_profiles(self) -> List[EncodingProfile]:
        """
        Ładuje profile kodowania z skonfigurowanego pliku JSON.
        Jeśli plik nie istnieje lub jest pusty/uszkodzony, zwraca pustą listę.
        """
        logger.debug(f"Profiler: Próba załadowania profili z {self.profiles_file_path}")
        if not self.profiles_file_path.exists():
            logger.info("Profiler: Plik profili nie znaleziony. Zwracanie pustej listy.")
            return []

        try:
            with open(self.profiles_file_path, 'r', encoding='utf-8') as f:
                # Użyj niestandardowego dekodera do obsługi obiektów Path (choć mało prawdopodobne dla profili)
                # i do zapewnienia poprawnego tworzenia obiektów ze słowników
                raw_profiles_data = json.load(f, cls=AppJSONDecoder)

            if not isinstance(raw_profiles_data, list):
                logger.error(f"Profiler: Zawartość pliku profili nie jest listą. Znaleziono: {type(raw_profiles_data)}. Zwracanie pustej listy.")
                return []

            loaded_profiles: List[EncodingProfile] = []
            for profile_data in raw_profiles_data:
                try:
                    # Sprawdź, czy profile_data jest słownikiem, zanim przekażesz do from_dict
                    if isinstance(profile_data, EncodingProfile): # Jeśli AppJSONDecoder już przekonwertował
                        loaded_profiles.append(profile_data)
                    elif isinstance(profile_data, dict):
                        profile = EncodingProfile.from_dict(profile_data)
                        loaded_profiles.append(profile)
                    else:
                        logger.warning(f"Profiler: Pomijanie nieprawidłowego wpisu profilu (nie jest słownikiem ani EncodingProfile): {profile_data}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Profiler: Pomijanie nieprawidłowego wpisu profilu podczas ładowania: {profile_data}. Błąd: {e}", exc_info=True)
                except Exception as e: # Inne nieoczekiwane błędy
                    logger.error(f"Profiler: Nieoczekiwany błąd przetwarzania wpisu profilu: {profile_data}. Błąd: {e}", exc_info=True)


            logger.info(f"Profiler: Pomyślnie załadowano {len(loaded_profiles)} profili.")
            return loaded_profiles

        except (json.JSONDecodeError, FileNotFoundError) as e: # ValueError już obsłużony w pętli
            logger.error(f"Profiler: Błąd ładowania profili z {self.profiles_file_path}: {e}. Zwracanie pustej listy.", exc_info=True)
            # Można dodać logikę backupu uszkodzonego pliku
            backup_path = self.profiles_file_path.with_suffix(f'.backup_load_error_{datetime.now():%Y%m%d%H%M%S}.json')
            try:
                if self.profiles_file_path.exists():
                    self.profiles_file_path.rename(backup_path)
                    logger.warning(f"Profiler: Utworzono kopię zapasową uszkodzonego pliku profili: {backup_path}")
            except Exception as backup_e:
                logger.error(f"Profiler: Nie udało się utworzyć kopii zapasowej pliku profili {self.profiles_file_path}: {backup_e}", exc_info=True)
            return [] # Zwróć pustą listę w przypadku błędu

    def _save_profiles(self):
        """Zapisuje bieżącą listę obiektów EncodingProfile do pliku JSON."""
        logger.debug(f"Profiler: Zapisywanie {len(self.profiles)} profili do {self.profiles_file_path}")
        try:
            # Konwertuj listę obiektów EncodingProfile na listę słowników
            # Używamy AppJSONEncoder, który wywoła metodę to_dict() dla każdego EncodingProfile
            with open(self.profiles_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.profiles, f, indent=4, cls=AppJSONEncoder) # Użyj niestandardowego enkodera
            logger.info(f"Profiler: Pomyślnie zapisano {len(self.profiles)} profili.")
        except Exception as e:
            logger.error(f"Profiler: Błąd zapisu profili do {self.profiles_file_path}: {e}", exc_info=True)

    def add_profile(self, profile: EncodingProfile, save: bool = True) -> EncodingProfile:
        """Dodaje nowy profil kodowania."""
        logger.debug(f"Profiler: Próba dodania profilu: {profile.name}")
        # Upewnij się, że profil ma unikalne ID, wygeneruj jeśli nie ma lub jest None
        if not isinstance(profile.id, uuid.UUID):
            profile.id = uuid.uuid4()
            logger.debug(f"Profiler: Wygenerowano nowe ID dla profilu '{profile.name}': {profile.id}")

        # Sprawdź duplikaty ID lub nazw (opcjonalne, ale dobra praktyka)
        if any(p.id == profile.id for p in self.profiles):
            logger.warning(f"Profiler: Profil z ID {profile.id} już istnieje. Nie dodawanie duplikatu.")
            raise ValueError(f"Profil z ID {profile.id} już istnieje.")
        if any(p.name.lower() == profile.name.lower() for p in self.profiles):
            logger.warning(f"Profiler: Profil o nazwie '{profile.name}' już istnieje. Nie dodawanie duplikatu.")
            raise ValueError(f"Profil o nazwie '{profile.name}' już istnieje.")

        self.profiles.append(profile)
        if save:
            self._save_profiles()
        logger.info(f"Profiler: Dodano nowy profil: {profile.name} (ID: {profile.id}).")
        return profile

    def get_profile_by_id(self, profile_id_str: str) -> Optional[EncodingProfile]:
        """Pobiera profil kodowania na podstawie jego ID (jako string)."""
        logger.debug(f"Profiler: Pobieranie profilu po ID: {profile_id_str}")
        try:
            target_id = uuid.UUID(profile_id_str)
        except ValueError:
            logger.warning(f"Profiler: Nieprawidłowy format UUID dla ID profilu: {profile_id_str}")
            return None

        for profile in self.profiles:
            if profile.id == target_id:
                logger.debug(f"Profiler: Znaleziono profil '{profile.name}' z ID: {target_id}.")
                return profile
        logger.warning(f"Profiler: Profil z ID {target_id} nie znaleziony.")
        return None

    def get_profile_by_name(self, profile_name: str) -> Optional[EncodingProfile]:
        """Pobiera profil kodowania na podstawie jego nazwy (ignoruje wielkość liter)."""
        logger.debug(f"Profiler: Pobieranie profilu po nazwie: '{profile_name}'")
        for profile in self.profiles:
            if profile.name.lower() == profile_name.lower():
                logger.debug(f"Profiler: Znaleziono profil '{profile.name}'.")
                return profile
        logger.warning(f"Profiler: Profil o nazwie '{profile_name}' nie znaleziony.")
        return None

    def update_profile(self, updated_profile: EncodingProfile) -> bool:
        """Aktualizuje istniejący profil kodowania."""
        logger.debug(f"Profiler: Próba aktualizacji profilu: {updated_profile.name} (ID: {updated_profile.id})")
        
        if not isinstance(updated_profile.id, uuid.UUID):
            logger.error("Profiler: Próba aktualizacji profilu bez prawidłowego ID UUID.")
            return False

        for i, profile in enumerate(self.profiles):
            if profile.id == updated_profile.id:
                # Sprawdź konflikt nazw, jeśli nazwa jest zmieniana
                if profile.name.lower() != updated_profile.name.lower() and \
                   any(p.name.lower() == updated_profile.name.lower() and p.id != updated_profile.id for p in self.profiles):
                    logger.warning(f"Profiler: Nie można zaktualizować profilu. Inny profil o nazwie '{updated_profile.name}' już istnieje.")
                    raise ValueError(f"Inny profil o nazwie '{updated_profile.name}' już istnieje.")

                self.profiles[i] = updated_profile
                self._save_profiles()
                logger.info(f"Profiler: Pomyślnie zaktualizowano profil: {updated_profile.name} (ID: {updated_profile.id}).")
                return True
        logger.warning(f"Profiler: Profil z ID {updated_profile.id} nie znaleziony do aktualizacji.")
        return False

    def delete_profile(self, profile_id_str: str) -> bool:
        """Usuwa profil kodowania na podstawie jego ID (jako string)."""
        logger.debug(f"Profiler: Próba usunięcia profilu z ID: {profile_id_str}")
        try:
            target_id = uuid.UUID(profile_id_str)
        except ValueError:
            logger.warning(f"Profiler: Nieprawidłowy format UUID dla ID profilu przy usuwaniu: {profile_id_str}")
            return False

        initial_count = len(self.profiles)
        self.profiles = [p for p in self.profiles if p.id != target_id]
        if len(self.profiles) < initial_count:
            self._save_profiles()
            logger.info(f"Profiler: Pomyślnie usunięto profil z ID: {target_id}.")
            return True
        logger.warning(f"Profiler: Profil z ID {target_id} nie znaleziony do usunięcia.")
        return False

    def get_all_profiles(self) -> List[EncodingProfile]:
        """Zwraca listę wszystkich załadowanych profili kodowania."""
        logger.debug("Profiler: Zwracanie wszystkich załadowanych profili.")
        return self.profiles

    def set_active_profile_id(self, profile_id: Optional[uuid.UUID]):
        """Ustawia ID aktywnego profilu w konfiguracji."""
        profile_id_str = str(profile_id) if profile_id else None
        self.config_manager.set_config_value('general', 'active_profile_id', profile_id_str)
        logger.info(f"Profiler: Ustawiono aktywne ID profilu na: {profile_id_str}")

    def get_active_profile(self) -> Optional[EncodingProfile]:
        """Pobiera aktualnie aktywny profil na podstawie ID zapisanego w konfiguracji."""
        active_profile_id_str = self.config_manager.get_config_value('general', 'active_profile_id')
        if active_profile_id_str:
            return self.get_profile_by_id(active_profile_id_str)
        return None

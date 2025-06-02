# src/repair_profiler.py
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import uuid
import sys 
import shutil 
from datetime import datetime 

from .config_manager import ConfigManager
from .models import RepairProfile, AppJSONEncoder, AppJSONDecoder

logger = logging.getLogger(__name__)

class RepairProfiler:
    """
    Zarządza profilami naprawy FFmpeg, włącznie z ładowaniem i zapisywaniem
    do pliku JSON.
    """
    def __init__(self, config_manager: ConfigManager):
        logger.debug("RepairProfiler: Inicjalizacja rozpoczęta.")
        self.config_manager = config_manager
        self.profiles_file_path: Path = self.config_manager.get_repair_profiles_file_full_path()
        logger.info(f"RepairProfiler: Używany plik profili naprawy: {self.profiles_file_path}")

        try:
            self.profiles_file_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"RepairProfiler: Upewniono się, że katalog profili naprawy istnieje: {self.profiles_file_path.parent}")
        except OSError as e:
            logger.critical(f"RepairProfiler: BŁĄD KRYTYCZNY: Nie można utworzyć katalogu dla profili naprawy {self.profiles_file_path.parent}: {e}", exc_info=True)
            
        self.profiles: List[RepairProfile] = self._load_profiles()
        if not self.profiles: 
            logger.info("RepairProfiler: Nie załadowano żadnych profili naprawy lub plik nie istnieje. Tworzenie domyślnych.")
            self._create_default_repair_profiles_if_empty()
        else:
            logger.info(f"RepairProfiler: Zainicjalizowano z {len(self.profiles)} profilami naprawy z {self.profiles_file_path}.")
        logger.debug("RepairProfiler: Inicjalizacja zakończona.")

    def _get_ffmpeg_params_with_tag_copy(self, base_params: List[str], copy_tags: bool) -> List[str]:
        """Dodaje parametry kopiowania tagów, jeśli copy_tags jest True i ich jeszcze nie ma."""
        params = list(base_params) 
        if copy_tags:
            has_manual_map_metadata = any(p.startswith('-map_metadata') for p in params)
            has_manual_map_chapters = any(p.startswith('-map_chapters') for p in params)

            if not has_manual_map_metadata:
                params.extend(['-map_metadata', '0'])
            
            if not has_manual_map_chapters:
                 params.extend(['-map_chapters', '0'])
        return params


    def _create_default_repair_profiles_if_empty(self):
        """Tworzy domyślne profile naprawy FFmpeg, jeśli lista jest pusta."""
        if self.profiles: 
            return

        logger.info("RepairProfiler: Tworzenie domyślnych profili naprawy FFmpeg.")
        default_profiles_data = [
            {
                "id": "d7f2c7a0-74f8-4f80-8a19-16a9ff7de4d5", 
                "name": "FFmpeg - Kopia Strumieni (domyślny)",
                "description": "Standardowa, szybka próba naprawy przez skopiowanie wszystkich strumieni, metadanych i rozdziałów.",
                "base_ffmpeg_params": ['-c', 'copy', '-map', '0', '-ignore_unknown', '-fflags', '+genpts'],
                "applies_to_mkv_only": False,
                "copy_tags": True
            },
            {
                "id": str(uuid.uuid4()),
                "name": "FFmpeg - Ignoruj Błędy Dekodowania",
                "description": "Próbuje skopiować strumienie, ignorując błędy dekodowania. Kopiuje metadane i rozdziały.",
                "base_ffmpeg_params": ['-err_detect', 'ignore_err', '-c', 'copy', '-map', '0', '-ignore_unknown'],
                "applies_to_mkv_only": False,
                "copy_tags": True
            }
        ]
        
        created_count = 0
        for profile_data in default_profiles_data:
            try:
                if not any(p.name == profile_data["name"] for p in self.profiles):
                    final_ffmpeg_params = self._get_ffmpeg_params_with_tag_copy(
                        profile_data["base_ffmpeg_params"],
                        profile_data["copy_tags"]
                    )
                    
                    new_profile = RepairProfile(
                        id=uuid.UUID(profile_data["id"]),
                        name=profile_data["name"],
                        description=profile_data["description"],
                        ffmpeg_params=final_ffmpeg_params,
                        applies_to_mkv_only=profile_data.get("applies_to_mkv_only", False),
                        copy_tags=profile_data["copy_tags"]
                    )
                    self.profiles.append(new_profile)
                    created_count += 1
            except ValueError as e:
                logger.error(f"RepairProfiler: Nie udało się utworzyć domyślnego profilu naprawy '{profile_data['name']}': {e}")

        if created_count > 0:
            self._save_profiles()
            logger.info(f"RepairProfiler: Utworzono i zapisano {created_count} domyślnych profili naprawy.")


    def _load_profiles(self) -> List[RepairProfile]:
        logger.debug(f"RepairProfiler: Próba załadowania profili naprawy z {self.profiles_file_path}")
        if not self.profiles_file_path.exists():
            logger.info("RepairProfiler: Plik profili naprawy nie znaleziony. Zwracanie pustej listy.")
            return []
        try:
            with open(self.profiles_file_path, 'r', encoding='utf-8') as f:
                raw_profiles_data = json.load(f, cls=AppJSONDecoder)
            if not isinstance(raw_profiles_data, list):
                logger.error(f"RepairProfiler: Zawartość pliku profili naprawy nie jest listą. Znaleziono: {type(raw_profiles_data)}. Zwracanie pustej listy.")
                self._backup_corrupted_profile_file("not_a_list")
                return []
            loaded_profiles: List[RepairProfile] = []
            for profile_data_item in raw_profiles_data:
                try:
                    if isinstance(profile_data_item, RepairProfile): loaded_profiles.append(profile_data_item)
                    elif isinstance(profile_data_item, dict): loaded_profiles.append(RepairProfile.from_dict(profile_data_item))
                    else: logger.warning(f"RepairProfiler: Pomijanie nieprawidłowego wpisu profilu naprawy: {profile_data_item}")
                except (ValueError, TypeError) as e: logger.warning(f"RepairProfiler: Pomijanie nieprawidłowego wpisu profilu naprawy podczas ładowania: {profile_data_item}. Błąd: {e}", exc_info=True)
            logger.info(f"RepairProfiler: Pomyślnie załadowano {len(loaded_profiles)} profili naprawy.")
            return loaded_profiles
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"RepairProfiler: Błąd ładowania profili naprawy z {self.profiles_file_path}: {e}. Zwracanie pustej listy.", exc_info=True)
            self._backup_corrupted_profile_file("load_error")
            return []
        except Exception as e_load:
             logger.error(f"RepairProfiler: Nieoczekiwany błąd ładowania profili naprawy: {e_load}", exc_info=True)
             self._backup_corrupted_profile_file("unexpected_error")
             return []

    def _backup_corrupted_profile_file(self, suffix_reason: str):
        try:
            backup_path = self.profiles_file_path.with_name(
                f"{self.profiles_file_path.name}.backup_{suffix_reason}_{datetime.now():%Y%m%d%H%M%S}"
            )
            if self.profiles_file_path.exists():
                shutil.copy2(self.profiles_file_path, backup_path)
                logger.warning(f"RepairProfiler: Utworzono kopię zapasową uszkodzonego pliku profili naprawy: {backup_path} (oryginał: {self.profiles_file_path})")
        except Exception as backup_e:
            logger.error(f"RepairProfiler: Nie udało się utworzyć kopii zapasowej pliku profili naprawy {self.profiles_file_path}: {backup_e}", exc_info=True)


    def _save_profiles(self):
        logger.debug(f"RepairProfiler: Zapisywanie {len(self.profiles)} profili naprawy do {self.profiles_file_path}")
        try:
            self.profiles_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.profiles_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.profiles, f, indent=4, cls=AppJSONEncoder)
            logger.info(f"RepairProfiler: Pomyślnie zapisano {len(self.profiles)} profili naprawy.")
        except Exception as e:
            logger.error(f"RepairProfiler: Błąd zapisu profili naprawy do {self.profiles_file_path}: {e}", exc_info=True)

    def add_profile(self, profile: RepairProfile, save: bool = True) -> RepairProfile:
        logger.debug(f"RepairProfiler: Próba dodania profilu naprawy: {profile.name}")
        if not isinstance(profile.id, uuid.UUID): profile.id = uuid.uuid4()
        if any(p.id == profile.id for p in self.profiles):
            raise ValueError(f"Profil naprawy z ID {profile.id} już istnieje.")
        if any(p.name.lower() == profile.name.lower() for p in self.profiles):
            raise ValueError(f"Profil naprawy o nazwie '{profile.name}' już istnieje.")
        
        profile.ffmpeg_params = self._get_ffmpeg_params_with_tag_copy(profile.ffmpeg_params, profile.copy_tags)
        self.profiles.append(profile)
        if save: self._save_profiles()
        logger.info(f"RepairProfiler: Dodano nowy profil naprawy: {profile.name} (ID: {profile.id}).")
        return profile

    def get_profile_by_id(self, profile_id_str: str) -> Optional[RepairProfile]:
        logger.debug(f"RepairProfiler: Pobieranie profilu naprawy po ID: {profile_id_str}")
        try: target_id = uuid.UUID(profile_id_str)
        except ValueError: logger.warning(f"Nieprawidłowy format UUID dla ID profilu naprawy: {profile_id_str}"); return None
        for profile in self.profiles:
            if profile.id == target_id: return profile
        return None

    def get_profile_by_name(self, profile_name: str) -> Optional[RepairProfile]:
        logger.debug(f"RepairProfiler: Pobieranie profilu naprawy po nazwie: '{profile_name}'")
        for profile in self.profiles:
            if profile.name.lower() == profile_name.lower(): return profile
        return None

    def update_profile(self, updated_profile: RepairProfile) -> bool:
        logger.debug(f"RepairProfiler: Próba aktualizacji profilu naprawy: {updated_profile.name} (ID: {updated_profile.id})")
        if not isinstance(updated_profile.id, uuid.UUID): return False
        for i, profile in enumerate(self.profiles):
            if profile.id == updated_profile.id:
                if profile.name.lower() != updated_profile.name.lower() and \
                   any(p.name.lower() == updated_profile.name.lower() and p.id != updated_profile.id for p in self.profiles):
                    raise ValueError(f"Inny profil naprawy o nazwie '{updated_profile.name}' już istnieje.")
                
                updated_profile.ffmpeg_params = self._get_ffmpeg_params_with_tag_copy(
                    updated_profile.ffmpeg_params, 
                    updated_profile.copy_tags
                )
                self.profiles[i] = updated_profile
                self._save_profiles()
                logger.info(f"RepairProfiler: Pomyślnie zaktualizowano profil naprawy: {updated_profile.name}.")
                return True
        logger.warning(f"Profil naprawy z ID {updated_profile.id} nie znaleziony do aktualizacji.")
        return False

    def delete_profile(self, profile_id_str: str) -> bool:
        logger.debug(f"RepairProfiler: Próba usunięcia profilu naprawy z ID: {profile_id_str}")
        try: target_id = uuid.UUID(profile_id_str)
        except ValueError: logger.warning(f"Nieprawidłowy format UUID dla ID profilu naprawy: {profile_id_str}"); return False
        initial_count = len(self.profiles)
        self.profiles = [p for p in self.profiles if p.id != target_id]
        if len(self.profiles) < initial_count:
            self._save_profiles()
            logger.info(f"RepairProfiler: Pomyślnie usunięto profil naprawy z ID: {target_id}.")
            return True
        logger.warning(f"Profil naprawy z ID {target_id} nie znaleziony do usunięcia.")
        return False

    def get_all_profiles(self) -> List[RepairProfile]:
        logger.debug("RepairProfiler: Zwracanie wszystkich załadowanych profili naprawy.")
        return list(self.profiles)

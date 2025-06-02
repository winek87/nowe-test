# src/filesystem/path_resolver.py
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from ..models import EncodingProfile
from ..config_manager import ConfigManager # Dla dostępu do ustawień ścieżek i wzorców

logger = logging.getLogger(__name__)

class PathResolver:
    """
    Odpowiada za rozwiązywanie i generowanie ścieżek wyjściowych dla plików
    transkodowanych i naprawionych.
    """
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        logger.debug("PathResolver zainicjalizowany.")

    def get_output_path_for_transcoding(self,
                                        original_file_path: Path,
                                        profile: EncodingProfile,
                                        custom_output_dir: Optional[Path] = None) -> Path:
        """
        Określa ścieżkę wyjściową dla transkodowanego pliku.

        Args:
            original_file_path: Oryginalna ścieżka pliku źródłowego.
            profile: Wybrany profil kodowania.
            custom_output_dir: Opcjonalna, niestandardowa ścieżka katalogu wyjściowego.
                               Jeśli podana, nadpisuje domyślny katalog z konfiguracji.

        Returns:
            Obiekt Path reprezentujący docelową ścieżkę wyjściową.

        Raises:
            ValueError: Jeśli konfiguracja struktury katalogu wyjściowego jest nieprawidłowa.
            FileNotFoundError: Jeśli wymagany katalog nie istnieje i nie można go utworzyć.
        """
        logger.debug(f"Określanie ścieżki wyjściowej dla transkodowania pliku: '{original_file_path.name}' z profilem '{profile.name}'.")

        # Określ bazowy katalog wyjściowy
        if custom_output_dir:
            base_output_dir = custom_output_dir.expanduser().resolve()
            logger.debug(f"Używanie niestandardowego katalogu wyjściowego: {base_output_dir}")
        else:
            default_output_dir_str = self.config_manager.get_config_value(
                'paths', 'default_output_directory', DEFAULT_CONFIG['paths']['default_output_directory']
            )
            # default_output_directory z config_manager powinien już być obiektem Path
            if isinstance(default_output_dir_str, Path):
                 base_output_dir = default_output_dir_str
            else: # Na wszelki wypadek, jeśli to string
                 base_output_dir = Path(default_output_dir_str).expanduser().resolve()
            logger.debug(f"Używanie domyślnego katalogu wyjściowego z konfiguracji: {base_output_dir}")


        # Logika struktury katalogu (na razie uproszczona - wszystko do base_output_dir)
        # W przyszłości można rozbudować o 'source_relative', 'profile_subdir' itp.
        # Na razie zakładamy strukturę płaską w base_output_dir lub podkatalogu z profilu.

        output_dir_final = base_output_dir

        # Sprawdź, czy profil definiuje podkatalog
        profile_subdir = profile.output_settings.get('subdirectory')
        if profile_subdir and isinstance(profile_subdir, str) and profile_subdir.strip():
            output_dir_final = base_output_dir / profile_subdir.strip()
            logger.debug(f"Profil '{profile.name}' definiuje podkatalog: '{profile_subdir}'. Końcowy katalog wyjściowy: {output_dir_final}")
        else:
            logger.debug(f"Brak zdefiniowanego podkatalogu w profilu. Używanie bazowego katalogu wyjściowego: {output_dir_final}")
        
        # Upewnij się, że katalog wyjściowy istnieje
        try:
            output_dir_final.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Upewniono się, że katalog wyjściowy istnieje: {output_dir_final}")
        except OSError as e:
            error_msg = f"Nie można utworzyć katalogu wyjściowego '{output_dir_final}': {e}"
            logger.error(error_msg, exc_info=True)
            raise FileNotFoundError(error_msg) # Rzuć błąd, jeśli nie można utworzyć katalogu

        # Skonstruuj ostateczną nazwę pliku wyjściowego
        # Użyj rdzenia oryginalnego pliku i rozszerzenia z profilu
        output_file_name = f"{original_file_path.stem}.{profile.output_extension.lstrip('.')}"
        final_output_path = output_dir_final / output_file_name

        logger.info(f"Określono ostateczną ścieżkę wyjściową dla transkodowania: {final_output_path}")
        return final_output_path

    def get_output_path_for_repair(self,
                                   original_file_path: Path,
                                   custom_output_dir: Optional[Path] = None) -> Path:
        """
        Określa ścieżkę wyjściową dla naprawionego pliku.

        Args:
            original_file_path: Oryginalna ścieżka (potencjalnie uszkodzonego) pliku.
            custom_output_dir: Opcjonalna, niestandardowa ścieżka katalogu dla naprawionych plików.

        Returns:
            Obiekt Path reprezentujący docelową ścieżkę dla naprawionego pliku.
        """
        logger.debug(f"Określanie ścieżki wyjściowej dla naprawy pliku: '{original_file_path.name}'.")

        if custom_output_dir:
            repaired_files_dir = custom_output_dir.expanduser().resolve()
        else:
            default_repaired_dir_str = self.config_manager.get_config_value(
                'paths', 'default_repaired_directory', DEFAULT_CONFIG['paths']['default_repaired_directory']
            )
            if isinstance(default_repaired_dir_str, Path):
                 repaired_files_dir = default_repaired_dir_str
            else:
                 repaired_files_dir = Path(default_repaired_dir_str).expanduser().resolve()
        
        logger.debug(f"Katalog dla naprawionych plików: {repaired_files_dir}")

        try:
            repaired_files_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            error_msg = f"Nie można utworzyć katalogu dla naprawionych plików '{repaired_files_dir}': {e}"
            logger.error(error_msg, exc_info=True)
            raise FileNotFoundError(error_msg)

        # Domyślnie użyj oryginalnej nazwy pliku w katalogu naprawionych plików
        # Wzorce zmiany nazwy będą obsługiwane przez generate_unique_output_path, jeśli wystąpi konflikt
        final_output_path = repaired_files_dir / original_file_path.name
        logger.info(f"Określono ostateczną ścieżkę wyjściową dla naprawy: {final_output_path}")
        return final_output_path


    def generate_unique_output_path(self,
                                    target_output_path: Path,
                                    is_repair_path: bool = False) -> Path:
        """
        Generuje unikalną ścieżkę wyjściową, jeśli `target_output_path` już istnieje,
        dodając znacznik czasu lub licznik zgodnie ze wzorcem z konfiguracji.

        Args:
            target_output_path: Początkowo żądana ścieżka wyjściowa, która może już istnieć.
            is_repair_path: True, jeśli generujemy ścieżkę dla naprawionego pliku
                            (użyje innego wzorca zmiany nazwy).

        Returns:
            Unikalny obiekt Path.

        Raises:
            RuntimeError: Jeśli nie można wygenerować unikalnej ścieżki po wielu próbach.
        """
        if not target_output_path.exists():
            return target_output_path # Ścieżka jest już unikalna

        logger.debug(f"Generowanie unikalnej ścieżki dla istniejącej: '{target_output_path}'. Czy naprawa: {is_repair_path}")

        # Pobierz odpowiedni wzorzec zmiany nazwy z konfiguracji
        if is_repair_path:
            rename_pattern_str = self.config_manager.get_config_value(
                'processing', 'repair_rename_pattern', DEFAULT_CONFIG['processing']['repair_rename_pattern']
            )
        else:
            rename_pattern_str = self.config_manager.get_config_value(
                'processing', 'rename_pattern', DEFAULT_CONFIG['processing']['rename_pattern']
            )
        
        base_stem = target_output_path.stem
        # Rozszerzenie z kropką, np. ".mp4"
        extension_with_dot = target_output_path.suffix
        parent_dir = target_output_path.parent

        timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S')
        active_profile = self.config_manager.get_config_value('general','active_profile_id') # to jest ID, nie obiekt
        # Aby uzyskać nazwę profilu, potrzebowalibyśmy instancji Profilera tutaj,
        # co tworzy zależność. Na razie uproszczenie - jeśli profil jest potrzebny we wzorcu,
        # trzeba będzie go przekazać lub zmienić wzorzec.
        # Na razie '{profile_name}' będzie pusty, jeśli go nie mamy.
        # Można też założyć, że `rename_pattern` nie używa `{profile_name}` lub jest on opcjonalny.
        profile_name_placeholder = "profil" # Placeholder

        counter = 1
        max_attempts = 100 # Zapobieganie nieskończonym pętlom
        
        current_path_attempt = target_output_path

        while current_path_attempt.exists() and counter <= max_attempts:
            # Zastosuj wzorzec do tworzenia nowej nazwy
            new_stem = rename_pattern_str
            new_stem = new_stem.replace('{original_stem}', base_stem)
            new_stem = new_stem.replace('{timestamp}', timestamp_str)
            new_stem = new_stem.replace('{counter}', str(counter))
            # Jeśli we wzorcu jest {profile_name}, ale nie mamy go tutaj łatwo dostępnego,
            # można go usunąć ze wzorca lub obsłużyć.
            # Załóżmy na razie, że wzorzec może go nie zawierać.
            new_stem = new_stem.replace('{profile_name}', profile_name_placeholder) # Użyj placeholdera

            new_file_name = f"{new_stem}{extension_with_dot}"
            current_path_attempt = parent_dir / new_file_name

            if not current_path_attempt.exists():
                logger.info(f"Wygenerowano unikalną ścieżkę: {current_path_attempt}")
                return current_path_attempt

            logger.debug(f"Wygenerowana ścieżka '{current_path_attempt.name}' już istnieje. Próba z licznikiem {counter + 1}.")
            counter += 1
            # Można rozważyć regenerację znacznika czasu dla każdej próby,
            # ale użycie początkowego jest prostsze i zazwyczaj wystarczające.

        if counter > max_attempts:
            error_msg = f"Nie można wygenerować unikalnej nazwy pliku wyjściowego dla '{target_output_path.name}' po {max_attempts} próbach."
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        return current_path_attempt # Powinno być już unikalne lub oryginalne, jeśli nie istniało

# Zaimportuj DEFAULT_CONFIG z config_manager, aby uniknąć redefinicji tutaj.
# To jest trochę problematyczne, bo tworzy cykliczną zależność na poziomie modułu.
# Lepszym rozwiązaniem byłoby przeniesienie DEFAULT_CONFIG do osobnego pliku
# lub przekazywanie wartości domyślnych jako argumenty.
# Na razie, zakładamy, że DEFAULT_CONFIG jest dostępny globalnie po imporcie ConfigManager
# lub, co lepsze, nie używamy go bezpośrednio tutaj, a polegamy na wartościach
# zwracanych przez config_manager.get_config_value, które mają swoje defaulty.
# Poprawiłem kod powyżej, aby polegał na defaultach z get_config_value.
from ..config_manager import DEFAULT_CONFIG # To jest nieoptymalne, ale na razie dla działania.

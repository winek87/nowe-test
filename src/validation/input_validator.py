# src/validation/input_validator.py
import logging
from pathlib import Path
from typing import List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

class InputValidator:
    """
    Klasa pomocnicza do walidacji różnych typów danych wejściowych od użytkownika
    lub z konfiguracji.
    """

    @staticmethod
    def is_valid_path(path_str: str, check_exists: bool = False, is_dir: Optional[bool] = None) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Sprawdza, czy podany ciąg znaków jest prawidłową ścieżką.
        Opcjonalnie sprawdza, czy ścieżka istnieje i czy jest katalogiem/plikiem.

        Args:
            path_str: Ciąg znaków reprezentujący ścieżkę.
            check_exists: Jeśli True, sprawdza, czy ścieżka fizycznie istnieje.
            is_dir: Jeśli True, sprawdza, czy ścieżka jest katalogiem.
                    Jeśli False, sprawdza, czy ścieżka jest plikiem.
                    Jeśli None, nie sprawdza typu.

        Returns:
            Krotka (isValid: bool, resolvedPath: Optional[Path], errorMessage: Optional[str])
        """
        if not path_str or not isinstance(path_str, str):
            return False, None, "Ścieżka nie może być pusta."

        try:
            resolved_path = Path(path_str).expanduser().resolve()
        except Exception as e:
            logger.warning(f"Błąd podczas rozwiązywania ścieżki '{path_str}': {e}")
            return False, None, f"Nieprawidłowy format ścieżki: {e}"

        if check_exists:
            if not resolved_path.exists():
                return False, resolved_path, "Podana ścieżka nie istnieje."

            if is_dir is True and not resolved_path.is_dir():
                return False, resolved_path, "Podana ścieżka nie jest katalogiem."
            elif is_dir is False and not resolved_path.is_file():
                return False, resolved_path, "Podana ścieżka nie jest plikiem."

        return True, resolved_path, None

    @staticmethod
    def get_integer_choice(prompt_message: str, min_val: Optional[int] = None, max_val: Optional[int] = None) -> Optional[int]:
        """
        Pobiera od użytkownika wybór będący liczbą całkowitą w określonym zakresie.
        Ta funkcja wymagałaby dostępu do obiektu `display` do wyświetlania promptu,
        więc na razie jest to bardziej szablon. W praktyce, metody promptujące
        powinny być w `CLIDisplay` lub `SettingsHandler`.

        Args:
            prompt_message: Komunikat do wyświetlenia użytkownikowi.
            min_val: Minimalna dopuszczalna wartość (włącznie).
            max_val: Maksymalna dopuszczalna wartość (włącznie).

        Returns:
            Wybrana liczba całkowita lub None, jeśli walidacja się nie powiodła.
        """
        # Ta metoda jest tutaj bardziej jako przykład; rzeczywista interakcja z użytkownikiem
        # powinna odbywać się poprzez CLIDisplay.
        # Tutaj symulujemy, że input_str został już pobrany.
        # input_str = display.get_user_choice(prompt_message) # Przykładowe użycie
        pass # Implementacja tej metody będzie zależeć od sposobu integracji

    @staticmethod
    def is_valid_file_extensions_list(extensions_str: str) -> Tuple[bool, List[str], Optional[str]]:
        """
        Waliduje listę rozszerzeń plików podaną jako string (np. ".mp4, .mkv, avi").
        Zwraca listę oczyszczonych rozszerzeń z kropką na początku.
        """
        if not isinstance(extensions_str, str):
            return False, [], "Lista rozszerzeń musi być tekstem."

        if not extensions_str.strip():
            return True, [], None # Pusta lista jest dozwolona

        raw_extensions = extensions_str.split(',')
        cleaned_extensions = []
        for ext in raw_extensions:
            ext = ext.strip()
            if not ext:
                continue
            if not ext.startswith('.'):
                ext = '.' + ext
            if len(ext) < 2 or not ext[1:].isalnum(): # Prosta walidacja (kropka + znaki alfanumeryczne)
                 return False, [], f"Nieprawidłowe rozszerzenie: '{ext}'. Rozszerzenia powinny składać się ze znaków alfanumerycznych."
            cleaned_extensions.append(ext.lower())

        if not cleaned_extensions:
             return False, [], "Nie podano prawidłowych rozszerzeń."
             
        return True, list(set(cleaned_extensions)), None # Usuń duplikaty

    # W przyszłości można dodać więcej metod walidacyjnych, np.:
    # - validate_ffmpeg_parameters(params: List[str]) -> bool
    # - validate_profile_name(name: str) -> bool
    # - validate_choice_from_options(choice: str, options: Dict[str, Any]) -> bool

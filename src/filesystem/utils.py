# src/filesystem/utils.py
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Ten plik jest przeznaczony na funkcje pomocnicze związane z systemem plików.
# Na przykład:
# - bezpieczne usuwanie plików/katalogów
# - tworzenie unikalnych nazw plików (choć część tej logiki jest w PathResolver)
# - sprawdzanie uprawnień do zapisu/odczytu
# - obliczanie rozmiaru katalogu

# def ensure_directory_exists(dir_path: Path) -> bool:
#     """Upewnia się, że podany katalog istnieje, tworząc go w razie potrzeby."""
#     try:
#         dir_path.mkdir(parents=True, exist_ok=True)
#         logger.debug(f"Katalog '{dir_path}' istnieje lub został utworzony.")
#         return True
#     except OSError as e:
#         logger.error(f"Nie można utworzyć katalogu '{dir_path}': {e}", exc_info=True)
#         return False

# def format_filesize(size_bytes: int) -> str:
#     """Formatuje rozmiar pliku w bajtach na czytelny format (KB, MB, GB)."""
#     if size_bytes < 1024:
#         return f"{size_bytes} B"
#     elif size_bytes < 1024**2:
#         return f"{size_bytes/1024:.2f} KB"
#     elif size_bytes < 1024**3:
#         return f"{size_bytes/1024**2:.2f} MB"
#     else:
#         return f"{size_bytes/1024**3:.2f} GB"

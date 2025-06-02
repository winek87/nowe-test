# src/cli_handlers/utils.py
import logging

logger = logging.getLogger(__name__)

# Ten plik jest przeznaczony na funkcje pomocnicze dla handlerów CLI.
# Przykłady potencjalnych funkcji:
# - parsowanie złożonych argumentów wprowadzanych przez użytkownika
# - funkcje formatujące specyficzne dla CLI, które nie pasują do CLIDisplay
# - pomocniki do nawigacji w bardziej skomplikowanych podmenu

# def parse_ffmpeg_params_from_string(params_str: str) -> List[str]:
#     """Prosty parser parametrów FFmpeg z ciągu znaków."""
#     # TODO: Dodać obsługę cudzysłowów, jeśli parametry zawierają spacje
#     return params_str.split()

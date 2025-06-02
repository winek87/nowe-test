# src/cli_styles.py

# Definicje kodów ANSI dla kolorów i stylów
ANSI_RESET = '\033[0m'
ANSI_BLACK = '\033[30m'
ANSI_RED = '\033[31m'
ANSI_GREEN = '\033[32m'
ANSI_YELLOW = '\033[33m'
ANSI_BLUE = '\033[34m'
ANSI_MAGENTA = '\033[35m'
ANSI_CYAN = '\033[36m'
ANSI_WHITE = '\033[37m'
ANSI_BRIGHT_BLACK = '\033[90m' # Używany jako domyślny kolor ramki, ale też dla opisów
ANSI_BRIGHT_RED = '\033[91m'
ANSI_BRIGHT_GREEN = '\033[92m'
ANSI_BRIGHT_YELLOW = '\033[93m'
ANSI_BRIGHT_BLUE = '\033[94m'
ANSI_BRIGHT_MAGENTA = '\033[95m'
ANSI_BRIGHT_CYAN = '\033[96m'
ANSI_BRIGHT_WHITE = '\033[97m'

# Kody ANSI dla tła
ANSI_BG_BLACK = '\033[40m'
ANSI_BG_RED = '\033[41m'
ANSI_BG_GREEN = '\033[42m'
ANSI_BG_YELLOW = '\033[43m'
ANSI_BG_BLUE = '\033[44m'
ANSI_BG_MAGENTA = '\033[45m'
ANSI_BG_CYAN = '\033[46m'
ANSI_BG_WHITE = '\033[47m'

# --- Style używane przez CLIDisplay (bazujące na ANSI) ---
STYLE_HEADER = f"{ANSI_BRIGHT_BLUE}"
STYLE_SEPARATOR = f"{ANSI_BRIGHT_BLACK}"
STYLE_INFO = f"{ANSI_WHITE}"
STYLE_SUCCESS = f"{ANSI_GREEN}"
STYLE_WARNING = f"{ANSI_YELLOW}"
STYLE_ERROR = f"{ANSI_BRIGHT_RED}"
STYLE_PROMPT = f"{ANSI_CYAN}"
STYLE_PROCESSING_FILE = f"{ANSI_MAGENTA}"
STYLE_PROGRESS_BAR_FILL = f"{ANSI_GREEN}"
STYLE_PROGRESS_BAR_EMPTY = f"{ANSI_BRIGHT_BLACK}"
STYLE_PROGRESS_TEXT = f"{ANSI_CYAN}"

STYLE_MENU_HIGHLIGHT = '\033[7m'
STYLE_MENU_DEFAULT = f"{ANSI_WHITE}"
STYLE_MENU_DESCRIPTION = f"{ANSI_BRIGHT_BLACK}" # <-- NOWY STYL DLA OPISÓW KATEGORII MENU

STYLE_CONFIG_VALUE = f"{ANSI_CYAN}"

# --- Ikony ---
ICON_ARROW_RIGHT = "▶"; ICON_SETTINGS = "⚙️"; ICON_PLAY = "🎬"; ICON_FOLDER_SCAN = "📂"; ICON_RESUME = "↪️"; ICON_STATUS = "📊"; ICON_PROFILE = "👤"; ICON_BROKEN_FILE = "💔"; ICON_REPAIR = "🛠️"; ICON_LIST = "📋"; ICON_CONFIG = "📝"; ICON_LOG = "📜"; ICON_MONITOR = "📈"; ICON_EXIT = "🚪"; ICON_WARNING = "⚠️"; ICON_ERROR = "❌"; ICON_SUCCESS = "✅"; ICON_INFO = "ℹ️"; ICON_DELETE = "🗑️"; ICON_SAVE = "💾"
ICON_PERCENT = "📊"; ICON_TIME_ETA = "⏱️"; ICON_FPS = "🎞️"; ICON_SPEED = "🚀"; ICON_BITRATE = "💾"; ICON_OUTPUT_SIZE = "📦"; ICON_CPU = "🖥️"; ICON_RAM = "🧠"; ICON_DISK = "💽"

# --- Znaki do rysowania ramek ANSI/Unicode ---
BOX_HL = "─"; BOX_VL = "│"; BOX_TL = "╭"; BOX_TR = "╮"; BOX_BL = "╰"; BOX_BR = "╯"

STYLE_FRAME = f"{ANSI_BLUE}" # Kolor ramki


# --- Style dla biblioteki Rich ---
RICH_STYLE_SYSTEM_MONITOR_HEADER = "bold bright_magenta"
RICH_STYLE_SYSTEM_MONITOR_LABEL = "bright_cyan"
RICH_STYLE_SYSTEM_MONITOR_VALUE = "white"
RICH_STYLE_PANEL_BORDER = "dim white"
RICH_STYLE_TABLE_TITLE = "bold bright_blue"
RICH_STYLE_CPU_WYSOKIE = "bold red"; RICH_STYLE_CPU_SREDNIE = "bold yellow"; RICH_STYLE_CPU_NISKIE = "bold green"
RICH_STYLE_RAM_WYSOKIE = "bold red"; RICH_STYLE_RAM_SREDNIE = "bold yellow"; RICH_STYLE_RAM_NISKIE = "bold green"
RICH_STYLE_DISK_LABEL_DEVICE = "cyan"; RICH_STYLE_DISK_LABEL_MOUNT = "green"; RICH_STYLE_DISK_LABEL_FSTYPE = "magenta"; RICH_STYLE_DISK_LABEL_SIZE = "dim white" 
RICH_STYLE_DISK_FREE_GOOD = "bright_green"; RICH_STYLE_DISK_FREE_LOW = "yellow" 
RICH_STYLE_FOOTER_TEXT = "italic dim white" 
RICH_STYLE_PANEL_TITLE = "bold white on blue"

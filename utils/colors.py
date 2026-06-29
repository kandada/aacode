import sys

# ── ANSI True Color helpers (no library dependency) ──
# Only apply colors in TTY mode; pipe mode (desktop client) stays untouched.


def _rgb_fg(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"


_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


# Colors follow the desktop client CSS theme for consistency
RED = (239, 68, 68)       # --color-error  #EF4444
GREEN = (34, 197, 94)     # --color-success  #22C55E
AMBER = (245, 158, 11)    # --color-warning  #F59E0B
BLUE = (59, 130, 246)     # #3B82F6
INDIGO = (99, 102, 241)   # observation  #6366F1
PURPLE = (167, 139, 250)  # thinking  #A78BFA
GRAY = (156, 163, 175)    # dim/meta  #9CA3AF
CYAN = (6, 182, 212)      # #06B6D4

_is_tty = sys.stdout.isatty()


def style(text, fg=None, bold=False, dim=False):
    """Wrap *text* with ANSI codes. No-op when not a TTY."""
    if not _is_tty or not text:
        return text
    codes = ""
    if fg:
        codes += _rgb_fg(*fg)
    if bold:
        codes += _BOLD
    if dim:
        codes += _DIM
    if not codes:
        return text
    return f"{codes}{text}{_RESET}"

"""Narrador amigável pro CLI — spinner animado, ANSI colors, mensagens em PT-BR.

Usado pra dar a sensação de "thinking..." no terminal, em vez de logs brutos.
Quando narrator está ativo, os logs `INFO` ficam silenciados; só `WARN`/`ERROR`
do pipeline aparecem (e mesmo esses passam pelo narrator quando possível).
"""

import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator

# ─── ANSI colors ────────────────────────────────────────────────────
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_GRAY = "\033[90m"

_SPINNER_FRAMES_UNICODE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_SPINNER_FRAMES_ASCII = ["|", "/", "-", "\\"]


def _supports_color() -> bool:
    return sys.stdout.isatty()


def _supports_unicode() -> bool:
    encoding = (sys.stdout.encoding or "").lower()
    return "utf" in encoding


def _c(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}" if _supports_color() else text


def _frames() -> list[str]:
    return _SPINNER_FRAMES_UNICODE if _supports_unicode() else _SPINNER_FRAMES_ASCII


class Narrator:
    """Imprime progresso bonito com spinner animado.

    Uso típico:

        narrator = Narrator()
        with narrator.step("pegando os últimos tickets do mês..."):
            tickets = fetch()
        narrator.done(f"{len(tickets)} tickets coletados")
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    # ──────────────────── primitives ────────────────────────────────

    @contextmanager
    def step(self, message: str) -> Iterator[None]:
        """Spinner roda em background enquanto o bloco executa."""
        if not self.enabled:
            yield
            return

        stop = threading.Event()
        frames = _frames()

        def spin() -> None:
            i = 0
            while not stop.is_set():
                frame = _c(frames[i % len(frames)], _CYAN)
                sys.stdout.write(f"\r  {frame}  {message}")
                sys.stdout.flush()
                time.sleep(0.08)
                i += 1

        thread = threading.Thread(target=spin, daemon=True)
        thread.start()

        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=0.2)
            # apaga a linha do spinner — quem chama escolhe printar `done` ou não
            sys.stdout.write("\r" + " " * (len(message) + 8) + "\r")
            sys.stdout.flush()

    def done(self, message: str) -> None:
        if self.enabled:
            print(f"  {_c('✓', _GREEN)}  {message}")

    def info(self, message: str) -> None:
        if self.enabled:
            print(f"  {_c('·', _DIM)}  {_c(message, _DIM)}")

    def warn(self, message: str) -> None:
        if self.enabled:
            print(f"  {_c('!', _YELLOW)}  {_c(message, _YELLOW)}")

    def fail(self, message: str) -> None:
        if self.enabled:
            print(f"  {_c('x', _RED)}  {_c(message, _RED)}")

    def section(self, title: str) -> None:
        if self.enabled:
            print()
            print(f"  {_c(title, _BOLD + _MAGENTA)}")
            print()

"""Logging estruturado com redação automática de segredos."""

import logging
import re
import sys

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(token|api[_-]?key|secret|password|webhook)\s*[:=]\s*\S+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"https://hooks\.slack\.com/\S+"),
)


class SecretRedactingFilter(logging.Filter):
    """Substitui padrões sensíveis por [REDACTED] em msg e args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            new_args = []
            for arg in record.args:
                new_args.append(self._redact(arg) if isinstance(arg, str) else arg)
            record.args = tuple(new_args)
        return True

    @staticmethod
    def _redact(text: str) -> str:
        out = text
        for pat in _SECRET_PATTERNS:
            out = pat.sub("[REDACTED]", out)
        return out


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(SecretRedactingFilter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # httpx loga cada GET/POST com URL inteira em INFO — vira ruído visual no
    # CLI sem agregar info útil (já temos log próprio por estágio). Sobe pra
    # WARNING; quem precisar de detalhe seta LOG_LEVEL=DEBUG.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

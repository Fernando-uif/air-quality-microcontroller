"""
sequence.py - Manejo de sequence number persistente
"""

SEQUENCE_FILE = "sequence.dat"


_current = 0


def load():
    """Carga el último sequence number del archivo local."""

    global _current

    try:
        with open(SEQUENCE_FILE, "r") as f:
            _current = int(f.read().strip())
    except (OSError, ValueError):
        _current = 0

    return _current


def next():
    """Incrementa y retorna el siguiente sequence number."""

    global _current
    _current += 1
    _save()
    return _current


def current():
    """Retorna el sequence actual sin incrementar."""
    return _current


def _save():
    """Guarda el sequence number en archivo local."""
    with open(SEQUENCE_FILE, "w") as f:
        f.write(str(_current))

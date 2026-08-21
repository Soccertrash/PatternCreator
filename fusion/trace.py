"""Zeilenprotokoll fuer die Schritte, die in Fusion haengen bleiben koennen.

Fusion kennt keinen Abbruch: bleibt ein API-Aufruf minutenlang stehen, sieht
man nur eine tote Anwendung, und hinterher laesst sich nicht mehr sagen,
**welcher** Aufruf es war. Deshalb schreibt jeder heikle Schritt eine Zeile -
sofort auf die Platte, ohne Puffer. Die letzte Zeile in der Datei ist dann der
Schuldige, und die Abstaende zwischen den Zeilen sind die Dauern.

Die Datei liegt auf dem Schreibtisch und beginnt bei jedem Erzeugen neu; sie
bleibt damit kurz und ist im Fehlerfall sofort zur Hand. Protokollieren darf
nie etwas kaputt machen: jeder Fehler dabei wird verschluckt.
"""

from __future__ import annotations

import os
import time
from typing import Optional

FILENAME = "PatternCreator-Log.txt"

_path: Optional[str] = None
_started = 0.0


def _target() -> str:
    home = os.path.expanduser("~")
    desktop = os.path.join(home, "Desktop")
    return os.path.join(desktop if os.path.isdir(desktop) else home, FILENAME)


def begin(title: str) -> None:
    """Protokoll neu anfangen."""
    global _path, _started
    _started = time.time()
    _path = _target()
    try:
        with open(_path, "w", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), title))
    except Exception:
        _path = None


def step(text: str) -> None:
    """Einen Schritt protokollieren - **vor** seiner Ausfuehrung."""
    if _path is None:
        return
    try:
        with open(_path, "a", encoding="utf-8") as fh:
            fh.write("%8.2f s  %s\n" % (time.time() - _started, text))
    except Exception:
        pass


def end(text: str) -> None:
    step("fertig - %s" % text)

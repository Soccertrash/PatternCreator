#!/usr/bin/env bash
#
# PatternCreator in den Fusion-Add-Ins-Ordner installieren.
#
#   ./install.sh              normale Installation
#   ./install.sh --dry-run    nur zeigen, was passieren wuerde
#   ./install.sh --force      auch bei laufendem Fusion installieren
#   ./install.sh --dir PFAD   abweichenden AddIns-Ordner verwenden
#
# Ablauf: pruefen ob das Add-In geladen sein kann -> vorhandene Installation
# loeschen -> Dateien frisch kopieren -> Ergebnis pruefen.

set -euo pipefail

ADDIN_NAME="PatternCreator"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FORCE=0
DRY_RUN=0
ADDINS_DIR=""

# Entwicklungs-Ballast, der nicht ins Add-In gehoert. ".git*" deckt das
# Repository (.git/), .gitignore und .gitattributes zusammen ab - in einer
# Installation hat nichts davon etwas zu suchen.
EXCLUDES=(".git*" ".venv" ".pytest_cache" "__pycache__" ".DS_Store" "*.pyc")

info()  { printf '  %s\n' "$*"; }
step()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$*"; }
fail()  { printf '\n\033[31mAbbruch:\033[0m %s\n\n' "$*" >&2; exit 1; }

usage() {
    sed -n '3,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        -f|--force)   FORCE=1 ;;
        -n|--dry-run) DRY_RUN=1 ;;
        --dir)        shift; [ $# -gt 0 ] || fail "--dir braucht einen Pfad."
                      ADDINS_DIR="$1" ;;
        -h|--help)    usage ;;
        *)            fail "Unbekannte Option „$1“. --help zeigt die Verwendung." ;;
    esac
    shift
done

# ---------------------------------------------------------------- Quelle

[ -f "$SRC/$ADDIN_NAME.manifest" ] && [ -f "$SRC/$ADDIN_NAME.py" ] \
    || fail "„$SRC“ enthaelt kein $ADDIN_NAME. Das Skript muss im Projektordner liegen."

manifest_version() {
    sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" | head -1
}
NEW_VERSION="$(manifest_version "$SRC/$ADDIN_NAME.manifest")"
[ -n "$NEW_VERSION" ] || fail "Im Manifest steht keine Version."

# ------------------------------------------------------------ Zielordner

# Autodesk hat den Ordner zwischen den Versionen umbenannt - beide Namen probieren.
find_addins_dir() {
    local candidates=()
    case "$(uname -s)" in
        Darwin)
            candidates=(
                "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns"
                "$HOME/Library/Application Support/Autodesk/Autodesk Fusion/API/AddIns"
            ) ;;
        MINGW*|MSYS*|CYGWIN*)
            candidates=(
                "${APPDATA:-}/Autodesk/Autodesk Fusion 360/API/AddIns"
                "${APPDATA:-}/Autodesk/Autodesk Fusion/API/AddIns"
            ) ;;
        *)
            return 1 ;;
    esac
    local dir
    for dir in "${candidates[@]}"; do
        [ -d "$dir" ] && { printf '%s\n' "$dir"; return 0; }
    done
    # Keiner existiert: den erstgenannten anlegen lassen
    printf '%s\n' "${candidates[0]}"
}

if [ -z "$ADDINS_DIR" ]; then
    ADDINS_DIR="$(find_addins_dir)" \
        || fail "Betriebssystem „$(uname -s)“ wird nicht unterstuetzt – Pfad mit --dir angeben."
fi
DEST="$ADDINS_DIR/$ADDIN_NAME"

step "1/4  Prüfen, ob das Add-In geladen ist"

# Fusion haelt ein laufendes Add-In komplett im Speicher; die Dateien sind dann
# nicht gesperrt, ein Austausch waehrend des Betriebs hinterlaesst aber einen
# halb alten Zustand. Von aussen laesst sich nur feststellen, OB Fusion laeuft -
# also gilt: laeuft Fusion, kann das Add-In geladen sein.
fusion_pids() {
    case "$(uname -s)" in
        Darwin)
            # [^/]* statt .* - sonst passen auch die Hilfsprozesse (Identity
            # Manager, QtWebEngine) unterhalb der Fusion-App.
            pgrep -f "Autodesk Fusion[^/]*\.app/Contents/MacOS/" 2>/dev/null || true ;;
        MINGW*|MSYS*|CYGWIN*)
            tasklist //NH //FI "IMAGENAME eq Fusion360.exe" 2>/dev/null \
                | grep -i "Fusion360.exe" | awk '{print $2}' || true ;;
        *)  printf '' ;;
    esac
}

PIDS="$(fusion_pids)"
if [ -n "$PIDS" ]; then
    warn "Fusion läuft (PID $(printf '%s' "$PIDS" | tr '\n' ' ' | sed 's/ $//'))."
    if [ "$FORCE" -eq 0 ]; then
        cat >&2 <<'TXT'

  Solange Fusion läuft, kann das Add-In geladen sein. Bitte zuerst:

    1. Dienstprogramme → Skripte und Add-Ins → Reiter „Add-Ins"
    2. PatternCreator markieren → Beenden
    3. Fusion schließen (sicherste Variante – Python-Module bleiben sonst
       aus der alten Fassung im Speicher)

  Danach ./install.sh erneut starten.
  Wer weiß, was er tut: ./install.sh --force

TXT
        exit 2
    fi
    warn "--force: es wird trotzdem installiert."
else
    ok "Fusion läuft nicht – das Add-In ist nicht geladen."
fi

step "2/4  Vorhandene Installation entfernen"
info "Ziel: $DEST"

if [ -e "$DEST" ]; then
    # Sicherung gegen ein falsch gesetztes --dir: nur einen Ordner loeschen, der
    # auch wirklich diese Installation ist.
    case "$DEST" in
        */AddIns/"$ADDIN_NAME") ;;
        *) fail "„$DEST“ liegt nicht in einem AddIns-Ordner – wird nicht gelöscht." ;;
    esac
    if [ ! -f "$DEST/$ADDIN_NAME.manifest" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
        fail "„$DEST“ enthält kein $ADDIN_NAME.manifest – wird sicherheitshalber nicht gelöscht."
    fi
    OLD_VERSION=""
    [ -f "$DEST/$ADDIN_NAME.manifest" ] && OLD_VERSION="$(manifest_version "$DEST/$ADDIN_NAME.manifest")"
    info "Installiert: Version ${OLD_VERSION:-unbekannt}  →  neu: Version $NEW_VERSION"
    if [ "$DRY_RUN" -eq 1 ]; then
        info "(Probelauf) würde gelöscht: $DEST"
    else
        rm -rf "$DEST"
        ok "Alte Installation gelöscht."
    fi
else
    ok "Noch nicht installiert – es wird neu angelegt."
fi

step "3/4  Dateien kopieren"

if [ "$DRY_RUN" -eq 1 ]; then
    info "(Probelauf) würde kopieren: $SRC  →  $DEST"
    info "ohne: ${EXCLUDES[*]}"
else
    mkdir -p "$DEST"
    if command -v rsync >/dev/null 2>&1; then
        rsync_args=()
        for pattern in "${EXCLUDES[@]}"; do rsync_args+=(--exclude "$pattern"); done
        rsync -a "${rsync_args[@]}" "$SRC/" "$DEST/"
    else
        # Ohne rsync: alles kopieren und den Ballast danach entfernen.
        cp -R "$SRC/." "$DEST/"
        for pattern in "${EXCLUDES[@]}"; do
            find "$DEST" -name "$pattern" -exec rm -rf {} + 2>/dev/null || true
        done
    fi
    ok "$(find "$DEST" -type f | wc -l | tr -d ' ') Dateien kopiert."
fi

step "4/4  Ergebnis prüfen"

if [ "$DRY_RUN" -eq 1 ]; then
    info "(Probelauf) – es wurde nichts verändert."
    exit 0
fi

STRAY="$(find "$DEST" \( -name ".git*" -o -name ".venv" -o -name "__pycache__" \
                       -o -name ".pytest_cache" -o -name "*.pyc" \) -print -quit)"
[ -z "$STRAY" ] || fail "Es wurde Entwicklungs-Ballast mitkopiert: $STRAY"
ok "Kein .git, kein .venv, keine Caches im Ziel."

INSTALLED="$(manifest_version "$DEST/$ADDIN_NAME.manifest" 2>/dev/null || true)"
[ "$INSTALLED" = "$NEW_VERSION" ] \
    || fail "Im Ziel steht Version „${INSTALLED:-keine}“ statt „$NEW_VERSION“."
[ -f "$DEST/$ADDIN_NAME.py" ] || fail "$ADDIN_NAME.py fehlt im Ziel."
[ -f "$DEST/palette/editor.html" ] || fail "Die Editor-Palette fehlt im Ziel."
ok "Version $NEW_VERSION installiert."

cat <<TXT

  Weiter in Fusion:

    1. Dienstprogramme → Skripte und Add-Ins → Reiter „Add-Ins"
    2. PatternCreator markieren → rechts muss **Version $NEW_VERSION** stehen
    3. Ausführen

TXT

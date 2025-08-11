# Druckerpreisrechner (Comfort-Version)

Dieses Paket enthält die Comfort-Version der App mit folgenden Features:
- Suche/Filter
- CSV-Export (Drucker, Verbrauchsmaterial, Vergleich)
- Automatische Übernahme von Cyan→Magenta/Yellow
- Profile speichern/laden
- Break-even-Berechnung gegenüber dem günstigsten Anschaffungspreis

## Dateien
- main.py — die Anwendung
- .github/workflows/build.yml — GitHub Actions Workflow zum Erstellen einer Windows .exe

## Schritt-für-Schritt Anleitung (für GitHub Web-UI, kein Git nötig)

1. GitHub-Account anlegen: https://github.com/join (falls noch nicht vorhanden).
2. Neues Repository erstellen (z.B. `druckerpreisrechner`).
3. Im neuen Repo: `Add file` → `Upload files`. Ziehe den Inhalt dieses ZIP in das Upload-Feld.
   Achte darauf, dass der Ordner `.github/workflows/build.yml` ebenfalls hochgeladen wird. Falls dein Browser das nicht zulässt, erstelle die Datei `build.yml` manuell in `.github/workflows/` und füge den Workflow-Inhalt ein.
4. Klicke `Commit changes` um die Dateien hochzuladen.
5. Öffne den Tab `Actions` → klicke auf den laufenden Build → warte bis er fertig ist.
6. Unter `Artifacts` findest du das Artefakt `druckerpreisrechner` — lade es runter (ZIP mit `main.exe`).
7. Die `.exe` kannst du auf deinem Windows-PC starten — kein Python nötig.

Wenn du Hilfe beim Hochladen brauchst, sag Bescheid — ich leite dich Schritt für Schritt durch den Prozess.

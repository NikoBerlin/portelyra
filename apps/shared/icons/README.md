# Bildmarke von Portelyra

`portelyra.svg` ist die Bildmarke von Portelyra, übernommen aus dem Favicon der Website. Die PNG-Dateien `portelyra-<Größe>.png`
sind daraus erzeugt, mit ImageMagick ohne Zeitstempel, damit sie bei jedem Erzeugen dieselben Bytes ergeben:

```
convert -background none -density 1536 portelyra.svg -resize <n>x<n> -strip \
  -define png:exclude-chunks=date,time,tIME,tEXt,zTXt,iTXt PNG32:portelyra-<n>.png
```

`desktop-entry` legt die Dateien als Symbol `portelyra` unter `$XDG_DATA_HOME/icons/hicolor/` ab. Starter und Hinweise am
Bildschirmrand nutzen dieses Symbol (#584). Fehlen die Dateien, bleibt es beim allgemeinen Symbol `applications-office`.

**Lizenz:** Der Name „Portelyra“ und die Bildmarke sind nicht Teil der Lizenz von Portelyra (AGPL-3.0-or-later). Rechte daran räumt
die AGPL nicht ein (Abschnitt 7 Buchstabe e), siehe Abschnitt „Lizenz“ im README.

# Backup zurückspielen – auch in einen anderen Ordner

Ein Backup lässt sich in jeden leeren Ordner zurückspielen, nicht nur in den ursprünglichen. Der
wiederhergestellte Bestand rechnet danach genauso wie vorher: Buchungen, FIFO, Bewertung, Tageshistorie und Snapshot.

## Ablauf

```
Rscript scripts/portelyra_desktop.R restore-preflight --bundle <backup> --target <neuer Ordner>
Rscript scripts/portelyra_desktop.R restore --bundle <backup> --target <neuer Ordner> --confirm RESTORE_TO_EMPTY_DESKTOP
PORTELYRA_DESKTOP_HOME=<neuer Ordner> Rscript scripts/portelyra_desktop.R install --confirm INSTALL_LOCAL_RUNTIME
PORTELYRA_DESKTOP_HOME=<neuer Ordner> Rscript scripts/portelyra_desktop.R start --browser firefox
```

Der Restore läuft in der Installation, die das Backup kennt (oder in einem Hilfs-Home mit derselben Kennung, siehe
[Passwortschutz → Notfall](passwortschutz.md#notfall-das-portelyra-home-ist-verloren)). Das Ziel muss leer sein oder fehlen.

## Was „Ursprungsort“ im Ergebnis bedeutet

Einige Speicher nehmen den Ordnerpfad des Datenbestands in ihre Prüfwerte auf: Wechselkurs-Abrufe, Wechselkurs-Sammelabruf,
Kurszuordnung, Bewertung, Kalender. An einem anderen Ort würden sie ihre eigenen Einträge ablehnen. Das schützt davor, dass eine
beliebige Kopie wie der echte Bestand behandelt wird.

Der Restore bindet den zurückgespielten Bestand deshalb selbst an seinen Ursprungsort. Er prüft den Ursprung zuerst gegen die
gespeicherten Prüfwerte und vermerkt ihn erst danach. Die Einträge selbst bleiben unverändert. Das Ergebnis nennt es in
`relocation`:

| `relocation` | Bedeutung |
|---|---|
| `not_needed` | Zurückgespielt an den ursprünglichen Ort – nichts zu tun. |
| `recorded` | Anderer Ort, Ursprung geprüft und vermerkt. |
| `present` | War schon vermerkt (etwa beim zweiten Aufruf). |
| `unverified` | Kein geprüfter Ursprung gefunden – siehe unten. |
| `not_possible` | Bestand nicht lesbar (etwa verschlüsselt und gesperrt) – nach dem Entsperren `relocate` ausführen. |

Den Ursprung findet der Restore in der laufenden Installation, sonst in den Aufträgen des Abschlusses. Meldet er `unverified`,
nennen Sie den alten Ordner des Datenbestands selbst:

```
PORTELYRA_DESKTOP_HOME=<neuer Ordner> Rscript scripts/portelyra_desktop.R relocate --confirm BIND_RESTORED_DATA_SPACE --origin <alter Pfad>/data/<tenant>/<user>/<data_space>
```

Ein falscher Pfad wird abgelehnt; vermerkt wird nur, was zu allen gespeicherten Prüfwerten passt.

**Von Hand kopierte Ordner** (etwa mit `cp` oder einem Dateimanager) bindet Portelyra nicht. Sie bleiben in den genannten Speichern
gesperrt, auch wenn die Vorlage selbst schon gebunden war. Nur der Restore oder ein bestätigtes `relocate` bindet.

**Woran man es merkt:** Ist der Bestand am neuen Ort nicht gebunden, hält „Alles aktualisieren“ vor den Kursen an.
Der Grund nennt die betroffenen Speicher und den Befehl `relocate`; er steht in allen Apps im Block links. Auch der Sammellauf im
Reiter Marktdaten startet dann nicht.

## Nach einem Umzug neu eintragen

- **Zugänge für Plugins** (Daten → Einstellungen → „Plugins und Zugänge“ → „Zugänge“): Sie gelten nur am Ort, an dem sie eingetragen wurden, und erscheinen am
  neuen Ort als „gehört zum Datenraum am ursprünglichen Ort“. Dort die Werte neu eintragen.
- **Passwortschutz:** Ein zurückgespieltes Home ist unverschlüsselt; den Schutz bei Bedarf neu einrichten.

## Proben

Vor jedem Release wird geprobt, dass ein Backup in einem anderen Ordner dieselben Ergebnisse liefert: Es wird dorthin zurückgespielt,
Bewertung, FIFO-Stand und Tageshistorie werden ohne Netz neu gerechnet und Tabelle für Tabelle mit dem gesicherten Stand verglichen.

# Signaturschlüssel

Portelyra signiert seine Releases und die Pakete der Steuermodule. Die Signatur belegt, dass ein Update
oder ein Steuermodul wirklich vom Herausgeber stammt und unterwegs nicht verändert wurde. Sie belegt die Herkunft, nicht die
Rechtsrichtigkeit eines Steuermoduls.

## Updates einspielen

Ein Update kommt als Archiv (`portelyra-<version>.tar.gz`). Eingespielt wird es **aus dem installierten Portelyra**, nicht aus dem
entpackten Archiv:

```
Rscript ~/.local/share/portelyra/library/.portelyra-source/scripts/portelyra_desktop.R update --archive <archiv> --confirm UPGRADE_LOCAL_RUNTIME
```

Einen anderen Weg für Updates gibt es nicht; der frühere Befehl `upgrade` verweist auf diesen. Warum aus dem installierten Portelyra: Wer einen Befehl aus dem entpackten Archiv startet, führt schon dessen Code aus – eine Prüfung
darin schützte nichts. So prüft das bereits installierte, vertraute Portelyra das neue Archiv, bevor daraus etwas läuft:

- jede Datei gegen ihre Prüfsumme im Release-Manifest;
- die Signatur des Manifests gegen die **Vertrauensliste des installierten Release** – nie gegen eine Liste, die das neue Archiv
  mitbringt.

Trägt die installierte Vertrauensliste noch keinen Schlüssel (Releases vor dem ersten Schlüssel), geht ein Update wie bisher ohne
Signatur. Sobald ein Release mit Schlüssel installiert ist, spielt Portelyra nur noch signierte Archive ein, ohne Ausnahme. Mögliche
Gründe für eine Ablehnung:

| Meldung | Bedeutung |
|---|---|
| `desktop_release_signature_missing` | Das Archiv trägt keine Signatur. Nicht einspielen, das Archiv von der Quelle neu beziehen. |
| `desktop_release_signature_untrusted` | Signiert, aber nicht mit einem Schlüssel von Portelyra. Nicht einspielen. |
| `desktop_release_signature_invalid` | Die Signatur passt nicht zum Inhalt; das Archiv wurde verändert. Nicht einspielen. |
| `desktop_release_update_entry_untrusted` | Der Befehl wurde nicht aus dem installierten Portelyra gestartet (siehe oben). |

`update` legt das Backup selbst an und prüft es, beendet und startet Portelyra und behält die drei jüngsten Backups:
[Update einspielen](update.md).

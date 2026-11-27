# Vorlage für ein Leser-Plugin

Herausgeber: (dein Name) · Version 0.1.0 · Schnittstelle `statement_reader_v1`, Stufe 4

Dieser Ordner ist eine **Vorlage**, kein mitgelieferter Leser. Ordner, die mit `_` beginnen, lädt Portelyra nicht. Er zeigt einen
vollständigen, kleinen Leser für eine CSV-Datei „Datum;Betrag;Text“ (Bereich `cash`) mit Erzeuger für den Selbsttest.

## Einen eigenen Leser entwickeln

1. Ordner kopieren und umbenennen, etwa nach `plugins/readers/meine_bank/` oder an einen beliebigen Ort außerhalb des Repositorys.
   `plugin_id` im Manifest muss dem Ordnernamen entsprechen; Leserkennungen enden auf `_vN`.
2. `reader_cash.py` (bzw. für Textbelege `read_text` und `detect`) an das Format des Instituts anpassen. Was ein Leser darf und
   muss, steht in `contracts/statement-reader-plugin/v1/README.md` unter „Mindestanforderungen“.
3. Einen **erfundenen** Testbeleg unter `fixtures/` ablegen, dazu das erwartete Ergebnis (`*.expected.json`). Aufbau echt, jede
   Zahl, jeder Name und jede Kennung erfunden.
4. `reader_generator.py` anpassen: Aus einem Startwert erfundene Buchungen würfeln, daraus den Beleg bauen und das erwartete
   Ergebnis **unabhängig vom Leser**.
5. Prüfsummen ins Manifest: `python3 dev/update_reader_manifests.py --apply --plugin <plugin_id>`, oder bei einem Ordner außerhalb
   von `plugins/readers` die SHA-256 von Einstieg und Modulen selbst eintragen.
6. Prüfen: `python3 dev/check_reader.py <pfad/zum/ordner> --seeds 1-50`. Mit `--documents <ordner>` liest das Werkzeug zusätzlich
   die eigenen echten Auszüge und zeigt nur Zählwerte und Gründe. Es schreibt nichts und schickt nichts weg.

## Vorlage: CSV „Datum;Betrag;Text“

| | |
|---|---|
| Bereich | Cash (Kontobewegungen) |
| Dokument | Umsatzliste (CSV) |
| Dateien | .csv |
| Erkennung | „datum + betrag + text“ |
| Geprüft | erfundene Beispieldateien |

Grenzen:

- Nur ein Beispiel: kein Saldo, keine Wertstellung, Zinsen am Wort „Zins“ erkannt.

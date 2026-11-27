# Import-Plugins: je Institut ein Mini-Handbuch

Portelyra trennt das **Basispaket** von den **Lesern einzelner Institute**. Das Basispaket bringt den Eingang mit Belegordner
und Ablage, die generischen CSV-Importer für Trades und Cash, den Aktivitäten-Import und die manuelle Erfassung mit
([Monatlicher Eingang](../monatlicher-eingang.md)). Die Leser für Banken, Broker, Börsen und Wallets kommen als **Plugins**. Sie liegen unter `plugins/readers/<institut>/` und
laufen abgeschottet. Schnittstelle,
Mindestanforderungen und Systemvoraussetzung (Linux ab Kernel 6.2): `contracts/statement-reader-plugin/v1/README.md`.
Die Seiten hier sind schon so geschrieben, dass sie als README in ihr Plugin wandern können.

## Aufbau jeder Seite

| Abschnitt | Inhalt |
|---|---|
| Steckbrief | Leser, Dokumente, Zeitraumregel, was die Dateien abdecken, geprüfter Formatstand |
| Herunterladen | der Weg beim Institut, Schritt für Schritt, mit den nötigen Einstellungen |
| Ablegen | Unterordner im Belegordner und was der Eingang daraus macht |
| Buchen | Reihenfolge der Importe, jeweils erst prüfen, dann buchen |
| Was gebucht wird | die Buchungsregeln des Lesers |
| Grenzen | was der Leser nicht kann oder bewusst nicht bucht, mit Ausweg |
| Steuerunterlagen | wo es sie gibt und wie sie abgelegt werden |

Die Seiten enthalten keine Werte eines bestimmten Portfolios.

## Plugins

| Institut | Stand | Leser | Seite |
|---|---|---|---|
| Smartbroker+ | aktiv | Wertpapiere, Devisen, Cash (Baader-Auszüge) | [smartbroker.md](smartbroker.md) |
| ING | aktiv | Wertpapiere, Cash | [ing.md](ing.md) |
| Scalable Capital | aktiv | Wertpapiere, Cash (Verrechnung, Tagesgeld) | [scalable.md](scalable.md) |
| Trade Republic | aktiv | Wertpapiere, Cash | [trade-republic.md](trade-republic.md) |
| DKB | aktiv | Cash (Umsatzliste, Kontoauszug) | [dkb.md](dkb.md) |
| C24 Bank | aktiv | Cash | [c24.md](c24.md) |
| Bondora | aktiv | Cash (Go & Grow) | [bondora.md](bondora.md) |
| Revolut | aktiv | Cash (Giro, Sparkonto) | [revolut.md](revolut.md) |
| Kraken | aktiv | Krypto, Rewards, Cash | [kraken.md](kraken.md) |
| Coinbase | aktiv | Krypto, Rewards, Cash | [coinbase.md](coinbase.md) |
| Bison | aktiv | Krypto, Rewards, Cash | [bison.md](bison.md) |
| BSDEX | aktiv | Krypto, Rewards, Cash | [bsdex.md](bsdex.md) |
| BitBox | aktiv | Krypto (Wallet) | [bitbox.md](bitbox.md) |
| Ledger | aktiv | Krypto (Wallet) | [ledger.md](ledger.md) |
| Baader Bank (Scalable-Depots aus der Baader-Zeit) | historisch | Wertpapiere, Cash | [historisch-und-von-hand.md](historisch-und-von-hand.md) |
| Bitcoin.de | aktiv | Krypto | [historisch-und-von-hand.md](historisch-und-von-hand.md) |
| CHECK24 Geldanlage | aktiv | Cash (Tagesgeld) | [historisch-und-von-hand.md](historisch-und-von-hand.md) |

## Neues oder noch nie gehaltenes Asset im Import

Ein Vorgang zu einem Asset, das der Katalog nicht kennt, bleibt ungebucht und steht als „ohne Katalogeintrag“ da; alles andere bucht der
Import. Zugeordnet wird bei Wertpapieren über die ISIN, bei Krypto über das Kürzel (erstes Wort des Namens oder in Klammern, etwa
„BTC (Bitcoin)“ oder „Bitcoin (BTC)“), bei Devisen über die Währung im Namen. Steht ein gleichnamiges Wertpapier ohne ISIN im Katalog,
bietet der Import „Vorhandenes … zuordnen“ an (die ISIN wird nachgetragen); sonst „Fehlendes Asset anlegen“ mit den Angaben aus dem
Beleg. Danach geht es zurück zum Import. Ein neu angelegtes Asset braucht noch eine **Kursquelle** (3. Marktdaten → 1. Kursquelle) –
ohne sie bleibt der Snapshot vor dem ersten Tag mit Bestand stehen; „Alles aktualisieren“ nennt dann das Asset.

## Vorabpauschalen: was automatisch eingetragen wird

Die Vorabpauschale je Fonds und Konto steht in Daten → Steuer → „Vorabpauschalen je Fonds und Konto“. Dorthin kommt sie auf drei Wegen:

| Weg | Institute | Was geschieht |
|---|---|---|
| automatisch aus dem Beleg | ING, Scalable Capital | Der Wertpapier-Import liest den Betrag vor Teilfreistellung. Fehlende trägt „Vorabpauschalen übernehmen“ ein; einen abweichenden Wert ersetzt er nur mit Häkchen. |
| nur geprüft | Trade Republic | Der Export nennt nur die einbehaltene Steuer. Der Import warnt, wenn der eingetragene Wert nicht dazu passt; der Betrag wird von Hand eingetragen. |
| von Hand | alle anderen | In der Karte eintragen. |

In der Ablage ist ein solcher Beleg ein **Jahresdokument der Art „Vorabpauschale“**: Der Eingang setzt die Art
selbst, wenn der Leser den Beleg erkennt. Belege, die kein Leser erkennt, gehören in `<Institut>/<Jahr>/Vorabpauschalen/` – mit
dem Jahr des Zuflusses, wie bei den Lesern: Die Vorabpauschale für 2024 fließt am ersten Werktag 2025 zu und gehört in den Ordner
2025 (siehe [Monatlicher Eingang](../monatlicher-eingang.md)).

## Für den Zuschnitt der Plugins

- **Ein Plugin je Institut** ist die Einheit, die jemand installiert: „Kraken“, nicht „Krypto-CSV-Leser“. Leser, die mehrere
  Institute teilen, werden darin zu einer gemeinsamen Bibliothek. Das sind der Krypto-Leser für Börsen und Wallets und der Leser für
  Perioden-Kontoauszüge der Baader Bank (Smartbroker+ und ältere Depots von Scalable Capital).
- **Je Plugin** gehören dazu: Manifest (Name, Version, Institut, Dokumentarten), Rezept für den Eingang (Downloads, Zeitraumregel,
  Unterordner), Erkennungsregeln, diese Seite als README und erfundene Testbelege mit dem echten Aufbau.
- **Im Basispaket bleibt**, was alle brauchen: Eingang und Ablage, die Regel „der neueste Export gilt“, Korrekturen neu verteilter
  Tage samt Saldoprobe und die generischen CSV-Importer – auch der experimentelle generische Leser für Institute ohne Plugin.

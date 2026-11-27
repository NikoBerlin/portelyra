# Plugins

Leser (lesen Ihre Belege), Kursanbieter (holen Kurse) und Steuermodule (rechnen die Steuer) sind Plugins.
Die meisten liefert Portelyra mit; weitere oder neuere Fassungen kommen als Paket (ZIP).

## Die Liste

Daten → Einstellungen → „Plugins und Zugänge“ → „Plugins“ zeigt alle auf einen Blick: Art, Version, ob mitgeliefert oder installiert, ob **von Portelyra
signiert** oder **ungeprüft**, und ob sie gerade wirken. Eingestellt werden sie in ihren Reitern: Leser unter Transaktionen → „Leser“
(an Ihren Belegen geprüft, aktiv je Portfolio), Kursanbieter unter „Kursanbieter“, die Fassung des Steuermoduls im Kasten „Regelmodul“.

## Paket installieren

In derselben Karte unter „Paket installieren“ die ZIP-Datei wählen und „Paket prüfen“. Portelyra erkennt am Paket, welche Art Plugin es
ist, und prüft es, bevor etwas installiert wird:

- **Leser:** Prüfsummen, Signatur (falls vorhanden) und der Selbsttest mit erfundenen Belegen. Installiert wird erst nach Ihrer
  Bestätigung; aktiv ist ein neuer Leser danach in keinem Portfolio.
- **Steuermodul:** nur mit Portelyra-Signatur, dazu Jahreswerte und Testfälle ([Steuer-Umfang](steuer-umfang.md)).
- **Kursanbieter:** Prüfsummen, Signatur (falls vorhanden), die Adressen, an die abgerufen wird, Kosten und Bedingungen, dazu der
  Selbsttest ohne Netz. Ein neuer Anbieter ist danach nicht aktiv; aktiviert wird er im Reiter „Kursanbieter“.

**Ungeprüft** heißt: Das Paket trägt keine Portelyra-Signatur – es liest Ihre Belege oder baut Kursabfragen mit Code eines anderen
Herausgebers. Das geht nur unter eigener Kennung und mit einer zusätzlichen Bestätigung.

## Updates mitgelieferter Plugins

Ein Paket mit derselben Kennung wie ein mitgelieferter Leser (etwa „Kraken“) oder Kursanbieter (etwa „Yahoo“) ist ein **Update**. Es wird nur installiert, wenn es von
Portelyra signiert ist und eine höhere Version trägt; dann gilt es sofort, die Aktivierung je Portfolio bleibt, und an Ihren Belegen
geprüft ist es erst wieder, wenn Sie eine Buchung damit bestätigen. Bringt ein späteres Release eine gleich hohe oder höhere Fassung mit,
gilt die mitgelieferte. Gilt die Signatur eines Updates nicht mehr, nimmt Portelyra ebenfalls die mitgelieferte.

**Zur vorigen Fassung** (Transaktionen → „Leser“ → „Installierte Plugins“, bei Kursanbietern im Reiter „Kursanbieter“) nimmt ein Update zurück: zur früher installierten Fassung,
sonst zur mitgelieferten. Die Aktivierung bleibt; Buchungen bleiben unverändert und tragen weiter die Fassung, mit der sie gelesen wurden.

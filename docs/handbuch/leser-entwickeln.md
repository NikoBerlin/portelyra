# Einen Leser entwickeln

Ein Leser liest die Belege eines Instituts: Kontoauszüge, Exporte, Abrechnungen. Er läuft als abgeschottetes Plugin. Prüfen,
Abgleich mit dem Bestand, Vorschau, Bestätigung und Buchen übernimmt Portelyra. Die genaue Schnittstelle und die
Mindestanforderungen stehen in `contracts/statement-reader-plugin/v1/README.md`. Diese Seite zeigt den Weg.

## Was ein Leser darf und was nicht

- Er liest nur den Beleg, den Portelyra ihm gibt. Kein Netz, keine anderen Dateien, kein Schreiben. Das erzwingt die Abschottung
  (Linux ab Kernel 6.2).
- Er liefert, was im Beleg steht, in der Form seines Bereichs, etwa Kontobewegungen (`cash`) oder Abrechnungen (`securities`).
  Er bucht nichts.
- Passt ein Beleg nicht oder ist er beschädigt, bricht er mit einem Code aus der festen Liste ab, statt abzustürzen.
- Jede Buchung trägt später, welcher Leser sie erzeugt hat: Plugin, Version, Prüfsumme des Codes.

## Schritt für Schritt

1. **Vorlage kopieren.** `plugins/readers/_template/` an einen beliebigen Ort kopieren und umbenennen, etwa `meine_bank/`. Im
   Manifest `plugin_id` auf den Ordnernamen setzen; die Leserkennung endet auf `_vN`, etwa `meine_bank_csv_v1`.
2. **Format verstehen.** Am besten an einem eigenen echten Auszug: Welche Spalten, welches Zahlenformat, welche Vorgangsarten? Der
   Auszug bleibt dabei auf dem Rechner; der Testbeleg im Plugin übernimmt nur den Aufbau, alle Werte sind erfunden.
3. **Leser schreiben.**
   - Belege als Bytes (`cash`, `reward`): `reader_cash.py` anpassen.
   - Textbelege (`securities`, `fx`, `crypto`, `income_statement`): `read_text` und `detect`; als Muster dienen die mitgelieferten
     Plugins.
   - Hilfen für Beträge, Tabellen und PDF-Text liefert das SDK `portelyra_reader_sdk_v1`.
   - Krypto-Exporte: Zeilen mit `for number, row in sheet.numbered(csv_dict_rows(text)):` zählen. Dann nennt die Vorschau eine verworfene
     Zeile mit ihrer Zeile in der Datei, ihrem Feld und dem Grund. Eigene Abbrüche: `sheet.skip("crypto_unreadable_row", number, feld, problem)`.
4. **Testbeleg anlegen.** Unter `fixtures/` einen Beleg mit echtem Aufbau, aber **erfundenen** Zahlen, Namen und Kennungen, dazu
   das erwartete Ergebnis (`*.expected.json`).
5. **Erzeuger schreiben.** `reader_generator.py` würfelt aus einem Startwert erfundene Vorgänge, baut daraus den Beleg und das
   erwartete Ergebnis. Das Ergebnis berechnet er **selbst**, ohne den Leser aufzurufen. Nur so prüft der Selbsttest etwas.
6. **Manifest pflegen.** Im Manifest stehen:
   - Erkennungsregeln (Wortgruppen, die jeder passende Beleg enthält);
   - getestete Formate samt Zeitraum und mindestens eine bekannte Grenze;
   - die Prüfsummen (SHA-256) von Einstieg und Modulen, etwa mit `sha256sum` ermittelt.
7. **Prüfen.** Den Selbsttest führt Portelyra beim Installieren selbst aus (siehe unten), in drei Stufen:
   - Testbelege genau, auch in frischen Prozessen und in vertauschter Reihenfolge;
   - verstümmelte Belege (Testbelege und erfundene) ohne Absturz und ohne Formfehler;
   - erfundene Belege aus dem Erzeuger genau getroffen.

## Plugin installieren

Ein fertiges Plugin geht als ZIP-Datei an den Nutzer – am besten als **Paket** mit einer `package.json`, die die Prüfsumme jeder
Datei nennt. Ein Paket ohne Signatur
installiert nur unter eigener Kennung und gilt als „ungeprüft“ (zusätzliche Bestätigung). Mit Portelyra-Signatur (nur der
Herausgeber Portelyra) gilt es als „von Portelyra signiert“; nur so kann ein Paket mit höherer Version einen mitgelieferten Leser
ablösen ([Plugins](plugins.md)). Der Nutzer installiert unter Daten → Einstellungen → „Plugins und Zugänge“ → „Plugins“ → „Paket installieren“. Portelyra entpackt die Datei sicher, prüft Manifest, Kennungen und Erzeuger und
führt den Selbsttest mit dem echten Datum aus. Installiert wird nur, was besteht. Danach ist das Plugin geladen, aber in keinem Portfolio
aktiv; aktiviert wird es in derselben Ansicht je Portfolio. Nach jedem Portelyra-Update testet Portelyra installierte Plugins neu. Wer ein
Plugin herausgibt, sollte daher nach Updates eine neue Fassung bereitstellen, falls der Test scheitert. Vorerst lassen sich Leser für Cash,
Wertpapiere, Devisen und Krypto installieren.

## Was der Selbsttest nicht leisten kann

Der Erzeuger stammt vom selben Autor wie der Leser. Deutet beide ein Format gleich falsch, merkt der Selbsttest es nicht. Deshalb
bucht ein Leser in einem Portfolio erst, nachdem Sie die Vorschau mit Ihren Belegen verglichen und das
ausdrücklich bestätigt haben – je Version des Plugins („an Ihren Belegen geprüft“). Nachgerechnet wird dabei nur, was der Beleg
selbst hergibt: Nennt er Salden, rechnet der Kern sie nach. Bei Exporten ohne Saldo (die meisten Krypto- und Reward-Exporte,
Abrechnungen) warnt die Vorschau deutlich, dass bis zur Bestätigung allein dieser Vergleich prüft.

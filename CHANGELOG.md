# Changelog

Neuerungen je öffentlicher Version von Portelyra. Die erste öffentliche Version ist die Beta 0.3.5.

## 0.3.5

Erste öffentliche Beta: Linux (Ubuntu 24.04), deutsche Oberfläche, ein Portfolio in Euro, deutsches Steuerrecht.

- **Einrichtung im Dialog:** zuerst ein Hinweis, was Portelyra nicht ist (keine Rechts-, Steuer- oder Anlageberatung, keine Gewähr),
  dann Umfang, wie Sie buchen – von Hand immer, auf Wunsch aus Belegen und Auszügen –, Ihre Institute samt Belegordner, Kurse,
  Zeitplan, Steuer und Passwortschutz mit Zusammenfassung; erst die Bestätigung gilt. Ohne Belege bietet Data weder Import noch
  Eingang an; zuschalten lässt es sich jederzeit in den Einstellungen unter „Umfang dieses Portfolios“.
- **Demo-Portfolio** mit erfundenem Bestand auf echten Assets, mit oder ohne aktuelle Kurse, getrennt von den eigenen Daten. Beim
  ersten Öffnen führt ein Rundgang in acht Schritten durch die vier Apps: Ein roter Pfeil zeigt auf das Bedienelement, „Zeig es mir“
  öffnet die Stelle, die Eingaben machen Sie selbst – mit einem Vorschlag für jedes Feld.
- **Buchungen** von Hand oder aus Belegen, mit Lesern für 17 Banken, Broker und Börsen. Jede Buchung erst als Vorschau mit Art, Tag
  und Wirkung, dann bestätigt; Korrektur und Storno lassen die frühere Fassung stehen. Leser laufen abgeschottet und verändern ihre
  Belege nicht; zu jedem Leser nennt der Import seine Grenzen, bei Rewards auch die Bewertung.
- **Cash** aus Kontoauszügen mit Abgleich der Salden.
- **Kurse** auf Wunsch von Yahoo Finance; ohne Anbieter bewertet Portelyra mit den Kursen der Buchungen oder eigenen Kursangaben.
- **Auswertung:** Tageshistorie, Rendite (TWR und IZF) je Zeitraum, Stichtag und Momentaufnahme, Vergleich, Gruppen, Projektion.
- **Steuer:** Regelmodul für 2020–2026 (2016–2019 in Grundzügen), Steuerreport in einfacher und ausführlicher Fassung (PDF, CSV),
  Rechenblatt je Ereignis bis zum einzelnen Lot, nach Topf vollständig aufgeschlüsselt – auch, was nicht besteuert wird; Krypto
  walletbezogen mit FIFO oder Durchschnitt. Kapitalerträge pauschal mit der Abgeltungsteuer.
- **Sichern:** Backup und Wiederherstellen in der App, Passwortschutz für Datenraum und Backups. Was Sie entsperrt haben, bleibt offen,
  bis Sie sich abmelden, den Rechner herunterfahren oder er in den Ruhezustand geht; danach fragt Portelyra nach dem Passwort. Öffnet ein
  Zeitplan den gesperrten Bestand, sperrt er ihn nach seinem Lauf wieder.
- **Updates finden:** „Nach Updates suchen“ in Daten → Einstellungen → „Programm“ fragt bei GitHub nach einer neueren Version und
  zeigt ihre Versionshinweise. Mit Zustimmung (Einrichtungsdialog, ohne Vorauswahl) sucht Portelyra einmal am Tag selbst; eine neuere
  Version steht dann links in jeder App. GitHub erfährt dabei die IP-Adresse, nichts aus dem Bestand. Eine neuere Version, die sich
  nicht einspielen lässt (etwa ohne passendes Archiv), nennt Portelyra mit Grund, statt „aktuell“ zu melden.
- **Updates einspielen** aus der App oder mit einem Befehl im Terminal. Jedes Update ist signiert und wird gegen die installierte
  Vertrauensliste geprüft; vorher legt Portelyra ein Backup an und prüft es. Aus der App zeigt eine eigene Seite die Schritte und bei
  einem Fehler den Grund und den Rückweg; danach zeigt Daten einmal, was neu ist.
- **Programm:** Reiter „Programm“ in den Einstellungen mit Version, „Neu in dieser Version“, Updates, Lizenz und der Wahl des
  Browsers: Standardbrowser des Systems (Vorgabe) oder ein auf dem Rechner gefundener Browser, auch als Snap oder Flatpak. Die Version
  steht auch unten im Block links jeder App.
- **Lizenz:** GNU AGPL, Version 3 oder später. Das Archiv enthält `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md` und den Vertrag für
  Leser-Plugins; der Reiter „Programm“ nennt Copyright und Bedingungen und zeigt den Lizenztext offline.
- **Hilfe** offline in jeder App, beim Abschnitt des offenen Reiters und über das „?“ an den Karten; „Erste Schritte“ am Demo mit einem
  erfundenen Beispielbeleg und ein Glossar der Fachbegriffe.
- **Bildmarke** im Anwendungsmenü und in den Hinweisen am Bildschirmrand.
- **Mindeststand:** Ubuntu 24.04 mit R 4.3 und Shiny 1.8 aus den Paketquellen; der Import von Belegen braucht Linux ab Kernel 6.2.

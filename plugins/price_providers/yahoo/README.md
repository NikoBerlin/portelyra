# Yahoo Finance (Kursanbieter-Plugin)

Mitgeliefertes Kursanbieter-Plugin (`price_provider_v1`, #495, seit rc.382). Kostenlos, ohne Schlüssel; Yahoo ist keine offizielle
Kursquelle. Abruf, Nutzung und die Einhaltung der Bedingungen von Yahoo verantwortet der Nutzer (Bedingungen: siehe `terms_url` im
Manifest).

- **Abruf nur im Kern:** Das Plugin baut die Anfrage und liest die Antwort; abgerufen wird von Portelyra, nur an
  `query1.finance.yahoo.com`.
- **Fähigkeiten:** Tageskurse (`daily_history`), Wechselkurse (`fx_daily_history`), Kurs der laufenden Sitzung (`quote`),
  Suche nach Name, Symbol oder ISIN (`search`), Symbol eines Währungspaares (`fx_symbol`).
- **Ausgänge je Antwort:** `ok`, `rejected` (Yahoo bremst: HTTP 429/503 oder Fehler im Körper), `not_listed` (Fenster vor der
  Erstnotiz: HTTP 400 „Data doesn't exist for startDate“), `invalid`, bei Sitzungskursen zusätzlich `no_observation`.
- **Bekannte Eigenheiten:** Ein Ein-Tages-Fenster liefert bei Börsennotierungen null Balken (der Kern weitet das Fenster auf);
  die Antwort trägt den laufenden Balken der offenen Sitzung, er wird getrennt ausgewiesen; auf `USDEUR=X` antwortet Yahoo auch mit
  der Kurzform `EUR=X`.
- **Selbsttest:** 14 erfundene Testantworten unter `fixtures/` (Erwartung aus dem Kern bis rc.381) und ein Erzeuger
  (`provider_generator.py`) für Tageskurse, Wechselkurse und Suche. Alle Symbole, Namen und Zahlen sind erfunden.

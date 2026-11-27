# Meldungen und nächste Schritte

Meldet eine App einen Grund, steht hier, was er bedeutet und was zu tun ist. Der Code am Ende jeder Meldung hilft beim Suchen
(Strg+F). Die Seite entsteht aus denselben Texten, die die Apps zeigen.

Steht bei einer Meldung „Bitte melden Sie diesen Fehlercode“, ist es kein Bedienfehler: Dann bitte ein Issue mit dem Code und dem,
was Sie zuletzt getan haben – ohne private Daten.

## Installation, Start und Update

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Der Datenraum ist nicht leer; die erste Einrichtung braucht einen leeren. | Den vorhandenen Datenraum weiter verwenden. | `desktop_onboarding_repository_not_empty` |
| Der Datenraum ist noch nicht angelegt. | Die Einrichtung abschließen. | `desktop_onboarding_repository_uninitialized` |
| Der Befehl oder eine Option ist ungültig. | Befehl und Optionen prüfen. | `desktop_product_cli_input_invalid` |
| Ein benötigtes Programm oder R-Paket fehlt. | Die Installation von Portelyra erneut ausführen; bleibt der Fehler, bitte melden. | `desktop_product_dependency_missing` |
| Der Datenordner liegt im Programmordner. | Einen Datenordner außerhalb des Programmordners wählen. | `desktop_product_home_inside_project` |
| Die Installation ist gescheitert. | Die Ausgabe des Befehls prüfen; bleibt der Fehler, bitte melden. | `desktop_product_install_failed` |
| Portelyra ist hier noch nicht eingerichtet. | Die Einrichtung starten. | `desktop_product_not_initialized` |
| Die Zugriffsrechte des Datenordners sind zu offen. | Den Ordner nur für das eigene Benutzerkonto freigeben. | `desktop_product_permissions_invalid` |
| Portelyra läuft nur unter Linux. | Ein unterstütztes Linux verwenden. | `desktop_product_platform_unsupported` |
| Die ältere Version kann den heutigen Datenstand nicht sicher schreiben. | Bei der aktuellen Version bleiben. | `desktop_product_rollback_incompatible` |
| Portelyra arbeitet gerade, etwa an einer Buchung oder einem Import. | Abwarten und erneut versuchen. | `desktop_product_update_busy` |
| Der neue Stand startet nicht. | Mit rollback zum bisherigen Stand zurückkehren und den Fehler melden. | `desktop_product_update_preflight_failed` |
| Portelyra hat sich nicht rechtzeitig beendet; nichts wurde eingespielt. | Portelyra beenden und das Update erneut starten. | `desktop_product_update_stop_failed` |
| Für die Abnahme fehlt ein abgeschlossener Abschluss. | Erst „Alles aktualisieren“ ausführen. | `desktop_release_acceptance_artifact_missing` |
| Am Ziel des Backups liegt schon etwas. | Einen anderen Ordner wählen oder in einer Minute erneut versuchen. | `desktop_release_backup_conflict` |
| Während des Backups hat sich der Datenraum geändert. | Warten, bis kein Vorgang mehr läuft, dann das Backup erneut starten. | `desktop_release_backup_source_changed` |
| Mit Passwortschutz muss das Backup im entsperrten, verschlüsselten Backup-Ordner liegen. | Portelyra entsperren und den vorgesehenen Backup-Ordner verwenden. | `desktop_release_backup_target_unprotected` |
| Die Zugriffsrechte des Ordners sind zu offen. | Den Ordner nur für das eigene Benutzerkonto freigeben. | `desktop_release_permissions_invalid` |
| Ein Release-Archiv mit diesem Namen, aber anderer Version gibt es schon. | Einen anderen Dateinamen wählen. | `desktop_release_release_conflict` |
| Am Ziel des Wiederherstellens liegt schon etwas. | Einen leeren oder neuen Ordner wählen. | `desktop_release_restore_conflict` |
| Das Backup gehört zu einem anderen Datenraum. | Ein Backup dieses Datenraums wählen oder in ein frisches Home wiederherstellen. | `desktop_release_restore_context_mismatch` |
| Das Backup stammt aus einer neueren Portelyra-Version. | Erst Portelyra aktualisieren, dann wiederherstellen. | `desktop_release_restore_newer_version` |
| Das Ziel für das Wiederherstellen ist nicht leer. | Einen leeren oder neuen Ordner wählen. | `desktop_release_restore_target_not_empty` |
| Portelyra läuft gerade oder ein anderer Vorgang hält den Datenraum. | Portelyra beenden, dann erneut versuchen. | `desktop_release_session_invalid` |
| Die Signatur des Update-Archivs passt nicht zu seinem Inhalt; das Archiv wurde verändert. | Nicht einspielen, das Archiv von der Quelle neu beziehen. | `desktop_release_signature_invalid` |
| Das Update-Archiv ist nicht mit einem Schlüssel von Portelyra signiert. | Nicht einspielen, das Archiv nur von der Portelyra-Quelle beziehen. | `desktop_release_signature_untrusted` |
| Ein Eintrag im Datenraum lässt sich nicht lesen (Ein-/Ausgabefehler), meist nach einem Neustart mitten in einem Lauf. | Im Handbuch „Backups“ den Abschnitt „Unlesbarer Eintrag“ befolgen, dann erneut versuchen. | `desktop_release_source_unreadable` |
| Im Datenraum ist ein Vorgang nicht abgeschlossen. | Portelyra starten, den Vorgang abschließen lassen, dann erneut versuchen. | `desktop_release_source_unsettled` |
| Ein Update muss aus dem installierten Portelyra gestartet werden. | Den Befehl wie im Handbuch „Signaturschlüssel“ beschrieben aus dem installierten Portelyra aufrufen. | `desktop_release_update_entry_untrusted` |
| Der Ordner taugt nicht als Belegordner: Er muss vorhanden sein, außerhalb des Datenbestands liegen und darf keine Verknüpfung sein. | Einen anderen Ordner wählen oder das Feld leer lassen und den Belegordner später im Eingang festlegen. | `desktop_setup_folder_invalid` |

## Passwortschutz

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Der Passwortschutz ist schon eingeschaltet. | Nichts weiter zu tun. | `desktop_protection_already_enabled` |
| Vor dem Löschen des Klartexts ist ein Backup im verschlüsselten Ordner nötig. | Erst ein Backup anlegen (Daten → „Einstellungen“ → „Sicherheit und Speicher“ → „Backups“). | `desktop_protection_backup_required` |
| Es gibt keinen verschlüsselten Backup-Ordner in diesem Benutzerkonto. | Den Passwortschutz prüfen. | `desktop_protection_backups_absent` |
| Es gibt schon einen verschlüsselten Backup-Ordner, etwa von einer früheren Einrichtung. | Den vorhandenen Ordner prüfen; die Einrichtung bietet an, wie es weitergeht. | `desktop_protection_backups_folder_exists` |
| Der verschlüsselte Backup-Ordner ist gerade von einer anderen Portelyra-Installation geöffnet. | Die andere Installation beenden, dann erneut versuchen. | `desktop_protection_backups_in_use` |
| Ein verschlüsselter Ordner ist schon eingehängt. | Die andere Portelyra-Sitzung beenden, dann erneut versuchen. | `desktop_protection_busy` |
| Die verschlüsselte Kopie stimmt nicht mit dem Original überein; nichts wurde gelöscht. | Den Vorgang erneut starten; bleibt der Fehler, bitte melden. | `desktop_protection_copy_mismatch` |
| Zum Erneuern des Schlüssels fehlt Platz: Alte und neue Ordner liegen zeitweise nebeneinander. | Platz schaffen, dann erneut versuchen. | `desktop_protection_disk_space` |
| Das Passwort im Schlüsselbund passt nicht mehr. | Auf der Startseite entsperren und „Mit der Anmeldung entsperren“ neu einschalten. | `desktop_protection_keyring_stale` |
| Der Schlüsselbund ist nicht erreichbar oder enthält das Passwort nicht. | Auf der Startseite mit dem Passwort entsperren. | `desktop_protection_keyring_unavailable` |
| Der verschlüsselte Ordner ließ sich nicht einhängen. | Portelyra neu starten; bleibt der Fehler, bitte melden. | `desktop_protection_mount_failed` |
| Es gibt noch keinen Datenraum. | Zuerst die App „Daten“ einmal öffnen und den Datenraum anlegen. | `desktop_protection_no_data_space` |
| Der Passwortschutz ist nicht eingeschaltet. | Ihn bei Bedarf in den Einstellungen einschalten. | `desktop_protection_not_enabled` |
| Nach dem Ruhezustand wird mit dem Passwort entsperrt. | Das Passwort eingeben; danach gilt auch der Schlüsselbund wieder. | `desktop_protection_password_after_sleep` |
| Die beiden Passwörter stimmen nicht überein. | Beide Felder gleich ausfüllen. | `desktop_protection_password_mismatch` |
| Das Passwort ist zu kurz (mindestens 10 Zeichen). | Ein längeres Passwort wählen. | `desktop_protection_password_too_short` |
| Das Passwort stimmt nicht. | Das Passwort erneut eingeben. | `desktop_protection_password_wrong` |
| Der Wiederherstellungsschlüssel stimmt nicht. | Den Schlüssel erneut eingeben. | `desktop_protection_recovery_key_invalid` |
| Das Erneuern des Schlüssels ist angefordert. | Auf der Startseite entsperren; dabei wird der Schlüssel erneuert. | `desktop_protection_rekey_pending` |
| Der Ordner für die entsperrte Ansicht (/run/user/…) ist nicht nutzbar. | Ab- und wieder anmelden, dann erneut versuchen. | `desktop_protection_runtime_dir_invalid` |
| Für den Passwortschutz fehlt das Programm gocryptfs. | gocryptfs über die Paketverwaltung installieren, dann erneut versuchen. | `desktop_protection_tool_missing` |
| Es gibt keinen unlesbaren Eintrag mehr. | Nichts weiter zu tun. | `desktop_protection_unreadable_none` |
| Darunter ist ein unlesbarer Eintrag, der weder ein abgeleiteter Lauf noch ein unfertiger Zwischenstand ist; ihn nimmt Portelyra nicht in Quarantäne. | Nichts selbst verschieben oder löschen; den Pfad melden (Handbuch „Backups“, „Unlesbarer Eintrag“). | `desktop_protection_unreadable_not_quarantinable` |
| Der Auftrag für die Quarantäne war nicht lesbar und wurde verworfen. | Erneut prüfen und bestätigen. | `desktop_protection_unreadable_request_invalid` |
| Der Befund hat sich seit der Vorschau geändert. | Erneut „Prüfen“ klicken und die neue Vorschau bestätigen. | `desktop_protection_unreadable_stale` |
| Nach mehreren falschen Eingaben ist eine kurze Pause nötig. | Kurz warten, dann erneut versuchen. | `desktop_protection_wait` |

## Buchungen und Stammdaten

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Der Entwurf gehört zu einem älteren Stand des Buchungsbestands. | Die Entwürfe neu laden und den Entwurf neu erstellen. | `activity_draft_source_superseded` |
| Die gewählte Buchung ist nicht mehr die aktuelle. | Die Liste neu laden und die Buchung erneut wählen. | `asset_activity_correction_predecessor_missing` |
| Für ein Asset oder Konto der Datei fehlt die Zuordnung. | Jedem Asset und Konto der Datei ein vorhandenes zuordnen. | `asset_activity_csv_mapping_required` |
| Eine Zeile verletzt Reihenfolge, Währung oder Buchungsregeln. | Die angezeigte Zeile in der Datei korrigieren und erneut einlesen. | `asset_activity_csv_row_blocked` |
| Der FIFO-Stand ist nicht mehr aktuell. | „Alles aktualisieren“ starten; es schreibt den FIFO-Stand fort. | `asset_activity_state_source_stale` |
| Das Asset gehört nicht zu diesem Portfolio. | Ein Asset dieses Portfolios wählen. | `asset_grouping_asset_scope_invalid` |
| Die Gruppe würde sich selbst enthalten. | Eine andere übergeordnete Gruppe wählen. | `asset_grouping_cycle_detected` |
| Das Datum „Gültig ab“ passt nicht zu den vorhandenen Zuordnungen. | Ein späteres Datum wählen. | `asset_grouping_effective_order_invalid` |
| Die Gruppe enthält noch Assets. | Erst die Zuordnungen entfernen, dann die Gruppe stilllegen. | `asset_grouping_group_not_empty` |
| Diese Gruppenzuordnung ist so nicht möglich. | Die übergeordnete Gruppe prüfen. | `asset_grouping_group_not_leaf` |
| Diese Gruppenzuordnung ist so nicht möglich. | Die übergeordnete Gruppe prüfen. | `asset_grouping_parent_invalid` |
| Die gewählte Referenz passt nicht zu dieser Rolle. | Eine passende Referenz wählen. | `asset_grouping_reference_role_invalid` |
| Die Einteilung enthält noch Gruppen. | Erst die Gruppen stilllegen, dann die Einteilung. | `asset_grouping_scheme_not_empty` |
| Die Mengengenauigkeit des Assets reicht schon aus. | Die Buchung ohne Anhebung fortsetzen. | `asset_quantity_scale_no_increase` |
| Die Menge braucht mehr als 24 Nachkommastellen. | Die Menge prüfen und kürzen. | `asset_quantity_scale_required_exceeds_limit` |
| Daran hängen noch aktive Einträge, etwa Konten oder Buchungen. | Erst die abhängigen Einträge stilllegen. | `catalog_command_dependency_active` |
| Die Stammdaten haben sich geändert; der Buchungsbestand muss angeglichen werden. | „Abschlussplan prüfen“ ausführen oder „Alles aktualisieren“ starten; beides gleicht an. | `desktop_asset_activity_canonical_changed` |
| Die ISIN ist ungültig. | Die zwölfstellige ISIN prüfen. | `desktop_catalog_isin_invalid` |
| Diese ISIN gehört schon zu einem anderen Asset. | Das vorhandene Asset verwenden. | `desktop_catalog_isin_taken` |

## Import

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Das Austauschpaket ist beschädigt oder unvollständig. | Das Paket neu exportieren. | `portfolio_csv_bundle_invalid` |
| Ein vorausgehender Schritt fehlt, etwa die Übernahme der Stammdaten. | Die Übergaben in der angezeigten Reihenfolge ausführen. | `portfolio_csv_handoff_dependency_missing` |
| Die Datei ließ sich nicht als Auszug lesen. | Datei und gewähltes Institut prüfen. | `securities_statement_source_invalid` |
| Eine Zeile oder Zuordnung ist doppelt. | Die doppelte Zuordnung entfernen. | `statement_import_mapping_duplicate_invalid` |
| Die Gebühr des Rewards ist nicht kleiner als seine Menge. | Gebühr und Menge prüfen. | `statement_import_mapping_quantity_invalid` |
| Die Zeitzone der Zeile passt nicht zur bestätigten Zeitzone. | Die Zeitzone prüfen. | `statement_import_mapping_timezone_invalid` |
| Das Zuordnungsprofil gehört zu einer anderen Fassung des Lesers. | Ein neues Zuordnungsprofil anlegen. | `statement_mapping_profile_adapter_mismatch` |
| Das Zuordnungsprofil enthält eine Zuordnung doppelt. | Die doppelte Zuordnung entfernen. | `statement_mapping_profile_duplicate_invalid` |
| Das gewählte Zuordnungsprofil gibt es nicht mehr. | Ein vorhandenes Profil wählen. | `statement_mapping_profile_ref_invalid` |

## Cash

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Für „vollständig abgestimmt“ fehlt der Anfangssaldo. | Den Anfangssaldo eintragen. | `cash_coverage_complete_opening_required` |
| Für „vollständig abgestimmt“ fehlt der Abstimmungsnachweis. | Den Saldo laut Auszug prüfen (Karte „Saldo prüfen“). | `cash_coverage_complete_reconciliation_required` |
| Eine Angabe zum Cash-Zeitraum ist ungültig. | Art, Betrag und Datum prüfen. | `cash_coverage_flow_classification_invalid` |
| Eine Angabe zum Cash-Zeitraum ist ungültig. | Art, Betrag und Datum prüfen. | `cash_coverage_income_invalid` |
| Die gewählte Art der Abdeckung ist hier nicht möglich. | Eine andere Art wählen oder den Stand des Kontos prüfen. | `cash_coverage_mode_invalid` |
| Eine Angabe zum Cash-Zeitraum ist ungültig. | Art, Betrag und Datum prüfen. | `cash_coverage_transfer_invalid` |
| Der Export nennt mehrere Konten. | Je Konto einen eigenen Export erstellen und einlesen. | `cash_statement_multiple_accounts` |
| Die Datei ließ sich nicht als Auszug lesen. | Datei und gewähltes Institut prüfen. | `cash_statement_source_invalid` |
| Die gewählte Art der Abdeckung ist hier nicht möglich. | Eine andere Art wählen oder den Stand des Kontos prüfen. | `desktop_cash_coverage_mode_invalid` |
| Der gewählte Zeitraum ist nicht mehr der aktuelle. | Die Liste neu laden und den Zeitraum erneut wählen. | `desktop_cash_coverage_predecessor_missing` |

## Kurse

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Für die Übergabe des Kalenders fehlen gespeicherte, geprüfte Profile. | Erst die Profile prüfen und speichern. | `desktop_market_fx_batch_calendar_saved_profile_required` |
| Ein vorheriger Abruf ist noch nicht übernommen. | Ihn zuerst übernehmen, dann erneut abrufen. | `desktop_market_fx_batch_calendar_staged_not_published` |
| Gewählte Bereiche warten nicht mehr oder können gerade nicht starten. | Die Liste neu laden und erneut wählen. | `desktop_market_fx_batch_selection_blocked` |
| Der Kursabruf wurde unterbrochen. | Den Abruf erneut starten. | `desktop_market_history_review_fetch_interrupted` |
| Der geprüfte Vorschlag wurde verworfen. | Bei Bedarf neu abrufen. | `desktop_market_history_review_rejected` |
| Diese Quelle ist für das Asset nicht eingerichtet. | Die Kurszuordnung prüfen. | `desktop_market_history_review_source_not_listed` |
| Es gibt einen Kurs für ein Asset ohne offenen Bestand. | Den überzähligen Kurs entfernen. | `manual_market_coverage_extra` |
| Für eine offene Position fehlt ein Kurs. | Den Kurs abrufen oder eintragen. | `manual_market_coverage_missing` |

## Alles aktualisieren und Abschluss

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Der letzte Abschluss lässt sich nicht lesen. | Einen neuen Abschluss starten, etwa mit „Alles aktualisieren“. | `desktop_run_center_last_run_unreadable` |
| Die Bewertung hat sich seit dem Abschlussplan geändert. | Den Abschlussplan neu prüfen und erneut bestätigen. | `desktop_run_center_market_valuation_changed` |
| Es gibt keinen unterbrochenen Abschluss zum Fortsetzen. | Einen neuen Abschluss starten. | `desktop_run_center_no_resumable_job` |
| Der Abschluss hielt bei der Analyse an. | „Alles aktualisieren“ erneut starten; bleibt der Fehler, bitte melden. | `desktop_workflow_analysis_blocked` |
| Der Abschluss hielt bei FIFO an: Die Buchungen ergeben keinen gültigen FIFO-Stand. | Die Buchungen prüfen (etwa ein Verkauf ohne vorherigen Bestand), dann „Alles aktualisieren“. | `desktop_workflow_fifo_blocked` |
| Vor dem ersten fortschreibenden Abschluss braucht es einen vollständigen Neuaufbau. | Den Abschluss einmal als „Vollständiger Neuaufbau“ ausführen. | `desktop_workflow_full_rebuild_required` |
| Der Abschluss hielt bei den Devisenkursen an. | Devisenkurse abrufen, dann „Alles aktualisieren“. | `desktop_workflow_fx_blocked` |
| Der Abschluss hielt bei der Gruppierung an. | Die eigenen Gruppen prüfen, dann „Alles aktualisieren“. | `desktop_workflow_grouping_blocked` |
| Der Abschluss hielt bei den Kursen an. | Kurse abrufen oder eintragen, dann „Alles aktualisieren“. | `desktop_workflow_market_blocked` |
| Der Abschluss hielt beim Veröffentlichen an. | „Alles aktualisieren“ erneut starten; bleibt der Fehler, bitte melden. | `desktop_workflow_publication_blocked` |
| Der Abschluss hielt bei der Steuer an. | Regelmodul und steuerliche Einordnung prüfen, dann „Alles aktualisieren“. | `desktop_workflow_tax_blocked` |
| Der Abschluss hielt bei der Bewertung an. | Kurse und Bewertungsart der Assets prüfen, dann „Alles aktualisieren“. | `desktop_workflow_valuation_blocked` |

## Steuer

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Die steuerliche Einordnung ist ungültig. | Die steuerliche Einordnung des Assets prüfen. | `tax_classification_invalid` |
| Für ein Asset fehlt die steuerliche Einordnung. | Die steuerliche Einordnung des Assets ergänzen. | `tax_classification_required` |
| Das Datum „Gültig ab“ ist ungültig oder liegt außerhalb der Jahre des Regelmoduls. | Ein Datum innerhalb der Jahre des Regelmoduls wählen. | `tax_configuration_effective_date_invalid` |
| Für dieses Datum gelten mehrere Regelmodule. | Die Auswahl unter Daten → „4. Steuer“ → „Regelmodul“ prüfen. | `tax_configuration_selection_ambiguous` |
| Für dieses Datum ist kein Regelmodul gewählt. | Daten → „4. Steuer“ → „Regelmodul wählen“. | `tax_configuration_selection_missing` |
| Diese Fassung ist schon installiert oder mitgeliefert. | Sie steht im Kasten „Regelmodul“ zur Übernahme bereit. | `tax_module_already_installed` |
| Installiert wird nur mit Ihrer Bestätigung. | Das Häkchen setzen und erneut installieren. | `tax_module_confirmation_required` |
| Die gewählte Datei ist keine lesbare ZIP-Datei oder zu groß. | Die ZIP-Datei des Steuermoduls wählen. | `tax_module_install_input_invalid` |
| Der Bereich der Steuermodule im Datenraum ist nicht schreibbar. | Den Datenraum entsperren, dann erneut versuchen. | `tax_module_install_store_invalid` |
| Die Beschreibung des Moduls ist ungültig oder passt nicht zum Paket. | Das Paket erneut von der Quelle beziehen. | `tax_module_manifest_invalid` |
| Eine Datei des Pakets weicht von ihrer signierten Prüfsumme ab oder fehlt. | Das Paket erneut von der Quelle beziehen. | `tax_module_package_file_mismatch` |
| Die Datei hat nicht den Aufbau eines Steuermodul-Pakets. | Das Paket erneut von der Quelle beziehen. | `tax_module_package_invalid` |
| Das Paket oder der Stand hat sich seit der Prüfung geändert. | Das Paket erneut prüfen. | `tax_module_preview_stale` |
| Die Testfälle des Pakets rechnen anders als angegeben. | Dieses Paket nicht verwenden und es melden. | `tax_module_selftest_failed` |
| Mit diesem Steuermodul kann diese Portelyra-Version noch nicht rechnen. | Portelyra aktualisieren oder ein passendes Modul wählen. | `tax_module_unsupported` |
| Die Jahreswerte, mit denen das Modul rechnet, stimmen nicht mit seiner Tabelle überein. | Dieses Paket nicht verwenden und es melden. | `tax_module_values_inconsistent` |
| Die Währungen von Portfolio, Buchung und FIFO passen nicht zusammen. | Die Kurswährung der betroffenen Assets prüfen; bleibt der Fehler, bitte melden. | `tax_report_v2_currency_invalid` |
| Im gewählten Steuerjahr gibt es keinen Verkauf. | Ein anderes Jahr wählen. | `tax_report_v2_no_disposals` |
| Die steuerliche Einordnung passt nicht zum gewählten Regelmodul. | Eine Einordnung des Regelmoduls wählen. | `tax_ui_classification_invalid` |
| Ein Steuerwert ist ungültig, etwa Währung oder Wertebereich. | Den Wert prüfen und korrigieren. | `tax_ui_parameter_invalid` |
| Die gewählte Fassung gibt es nicht mehr. | Die Ansicht neu laden. | `tax_ui_revision_missing` |

## Plugins und Zugänge

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Das Plugin kann einen Zugang nicht selbst prüfen. | Den Zugang mit einem Abruf testen. | `plugin_credentials_check_unsupported` |
| Für das Plugin gibt es mehrere Zugänge, aber keine Wahl. | Unter Daten → „Einstellungen“ → „Plugins und Zugänge“ → „Zugänge“ einen Zugang wählen. | `plugin_credentials_choice_required` |
| Das Plugin verlangt andere Felder als eingetragen. | Den Zugang mit den neuen Feldern neu eintragen. | `plugin_credentials_fields_changed` |
| Das Plugin will eine Adresse ansprechen, die für den Zugang nicht bestätigt ist. | Den Zugang mit den neuen Adressen erneut bestätigen. | `plugin_credentials_hosts_unconfirmed` |
| Der Schlüsselbund hat das Ablegen oder Entfernen abgelehnt. | Den Schlüsselbund entsperren, dann erneut versuchen. | `plugin_credentials_keyring_failed` |
| Für das Plugin ist kein Zugang eingetragen, oder sein Wert fehlt im Schlüsselbund. | Den Zugang unter Daten → „Einstellungen“ → „Plugins und Zugänge“ → „Zugänge“ eintragen. | `plugin_credentials_missing` |
| Der Zugang wurde an einem anderen Ort eingetragen, etwa vor einem Umzug des Datenraums. | Den Zugang hier neu eintragen. | `plugin_credentials_other_location` |
| Das Plugin ist nicht geladen oder braucht keinen Zugang. | Prüfen, ob das Plugin aktiviert ist. | `plugin_credentials_plugin_unavailable` |
| Die Signatur passt nicht zum Inhalt des Pakets; es wurde nach dem Signieren verändert. | Das Paket erneut von der Quelle beziehen. | `plugin_signature_invalid` |
| Das Paket trägt keine Portelyra-Signatur. | Nur Pakete mit Portelyra-Signatur installieren. | `plugin_signature_missing` |
| Die Signatur lässt sich nicht prüfen, weil ssh-keygen fehlt. | Das Paket openssh-client installieren und erneut prüfen. | `plugin_signature_tool_missing` |
| Die Signatur stammt von keinem Schlüssel der Vertrauensliste, oder der Schlüssel ist noch nicht eingerichtet. | Nur Pakete von Portelyra verwenden; bis der Schlüssel eingerichtet ist, lässt sich nichts installieren. | `plugin_signature_untrusted` |
| Das Kursanbieter-Plugin ist abgestürzt oder hat ein unlesbares Ergebnis geliefert. | Später erneut versuchen; bleibt der Fehler, bitte melden. | `price_provider_failed` |
| Das Plugin bietet diese Funktion nicht an. | Einen anderen Kursanbieter wählen. | `price_provider_operation_unsupported` |
| Die Antwort des Kursanbieters ist zu groß. | Einen kürzeren Zeitraum abrufen. | `price_provider_response_too_large` |
| Für diesen Kursanbieter gibt es kein gültiges Plugin. | Prüfen, ob das Plugin installiert und aktiviert ist. | `price_provider_unavailable` |
| Der Leser ist abgestürzt oder hat einen unbekannten Code gemeldet. | Die Datei prüfen; bleibt der Fehler, bitte melden. | `statement_reader_failed` |
| Eine Leserkennung ist schon von einem anderen Plugin belegt. | Eines der beiden Plugins entfernen. | `statement_reader_id_conflict` |
| Der Leser ist nicht installiert, oder seine Prüfsumme stimmt nicht. | Den Leser neu installieren und aktivieren. | `statement_reader_unavailable` |

## Anzeige

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Es gibt noch keinen veröffentlichten Stand. | In der App „Daten“ „Alles aktualisieren“ ausführen, dann neu lesen. | `display_no_latest` |
| Kurse und Assets mit Bestand passen nicht zusammen. | Kurse abrufen oder eintragen, dann den Snapshot erneut erstellen. | `portfolio_snapshot_v2_market_coverage_invalid` |
| Ein Bestand wäre negativ. | Die Buchungen prüfen: Meist fehlt ein Kauf oder Eingang vor einem Verkauf. | `portfolio_snapshot_v2_non_cash_inventory_negative` |

## Allgemein (gilt für viele Bereiche)

| Meldung | Nächster Schritt | Code |
|---|---|---|
| Das gewählte Konto ist nicht gültig. | Das Konto neu wählen; nach Änderungen die Ansicht neu laden. | `…_account_invalid` |
| Der Leser ist abgestürzt oder hat ein unlesbares Ergebnis geliefert. | Die Datei prüfen; bleibt der Fehler, bitte melden. | `…_adapter_failed` |
| Dieser Schritt wurde schon ausgeführt. | Die Ansicht neu laden. | `…_already_committed` |
| Die Angabe ist nicht eindeutig. | Genauer auswählen. | `…_ambiguous` |
| Ein Betrag ist ungültig. | Den Betrag prüfen und korrigieren. | `…_amount_invalid` |
| Das Plugin verlangt eine neuere Portelyra-Version. | Portelyra aktualisieren oder eine passende Fassung des Plugins verwenden. | `…_api_version_unsupported` |
| Das gewählte Asset ist nicht gültig. | Das Asset neu wählen; nach Änderungen die Ansicht neu laden. | `…_asset_invalid` |
| Ein früherer, unterbrochener Versuch passt nicht zu diesem Schritt. | Den unterbrochenen Vorgang zuerst abschließen; bleibt der Fehler, bitte melden. | `…_attempt_conflict` |
| Der Schritt ist blockiert. | Den angezeigten Grund beheben, dann erneut versuchen. | `…_blocked` |
| Gerade läuft ein anderer Vorgang, etwa „Alles aktualisieren“ oder ein Backup. | Warten, bis er beendet ist, dann erneut versuchen. | `…_busy` |
| Der Vorgang wurde abgebrochen. | Bei Bedarf erneut starten. | `…_cancelled` |
| Der gewählte Vorschlag ist nicht mehr gültig. | Die Vorschläge neu laden und erneut wählen. | `…_candidate_invalid` |
| Die Stammdaten lassen sich gerade nicht lesen. | Die Ansicht neu laden; bleibt der Fehler, bitte melden. | `…_catalog_unavailable` |
| Die Daten haben sich inzwischen geändert. | Die Ansicht neu laden und den Schritt wiederholen. | `…_changed` |
| Diese Bestätigung wurde schon verwendet. | Für einen weiteren Schritt eine neue Vorschau erstellen. | `…_confirmation_consumed` |
| Diese Bestätigung wurde schon verwendet. | Für einen weiteren Schritt eine neue Vorschau erstellen. | `…_confirmation_duplicate` |
| Die Bestätigung ist abgelaufen. | Die Vorschau neu erstellen und dann bestätigen. | `…_confirmation_expired` |
| Die Bestätigung passt nicht zur gezeigten Vorschau. | Die Vorschau neu erstellen und dann bestätigen. | `…_confirmation_invalid` |
| Die Bestätigung passt nicht zur gezeigten Vorschau. | Die Vorschau neu erstellen und dann bestätigen. | `…_confirmation_mismatch` |
| Der Schritt ist noch nicht bestätigt. | Erst die Vorschau ansehen, dann bestätigen. | `…_confirmation_missing` |
| Der Schritt ist noch nicht bestätigt. | Erst die Vorschau ansehen, dann bestätigen. | `…_confirmation_required` |
| Der Eintrag widerspricht einem vorhandenen. | Die vorhandenen Einträge prüfen und doppelte Angaben entfernen. | `…_conflict` |
| Diese Bestätigung wurde schon verwendet. | Für einen weiteren Schritt eine neue Vorschau erstellen. | `…_consumed` |
| Die Auswahl gehört zu einem anderen Stand als die Ansicht. | Die Ansicht neu laden und erneut wählen. | `…_context_mismatch` |
| Die Obergrenze an Abrufen ist erreicht, oder der Anbieter hat wegen zu vieler Abrufe abgewiesen. | Später erneut versuchen oder die Obergrenze unter „Zugänge“ anheben. | `…_cost_limit` |
| Für den Anbieter ist kein bereiter Zugang eingetragen. | Den Zugang unter Daten → „Einstellungen“ → „Plugins und Zugänge“ → „Zugänge“ eintragen. | `…_credential_unavailable` |
| Die Währung ist ungültig. | Einen dreistelligen Währungscode wie EUR oder USD angeben. | `…_currency_invalid` |
| Die Währung passt nicht zur Kurswährung der Notierung. | Kurswährung und Kurszuordnung prüfen. | `…_currency_mismatch` |
| Ein Datum ist ungültig. | Das Datum prüfen und korrigieren. | `…_date_invalid` |
| Ein Betrag oder eine Menge ist ungültig. | Die Zahl prüfen und korrigieren. | `…_decimal_invalid` |
| Die Funktion ist ausgeschaltet. | Sie in den Einstellungen einschalten, falls gewünscht. | `…_disabled` |
| Der Eintrag ist doppelt. | Die vorhandenen Einträge prüfen und doppelte Angaben entfernen. | `…_duplicate` |
| Diesen Eintrag gibt es schon. | Den vorhandenen Eintrag verwenden. | `…_duplicate_conflict` |
| Es gibt nichts zu verarbeiten. | Eine Datei mit Inhalt wählen oder die Auswahl erweitern. | `…_empty` |
| Die Datei hat eine unerwartete Zeichenkodierung. | Die Datei als UTF-8 speichern und erneut wählen. | `…_encoding_invalid` |
| Das Plugin weicht von seiner Prüfsumme ab und wird nicht geladen. | Das Plugin neu installieren. | `…_entry_mismatch` |
| Eine Grenze ist überschritten. | Weniger auf einmal verarbeiten. | `…_exceeded` |
| Den Eintrag oder die Datei gibt es schon. | Den vorhandenen Eintrag verwenden oder einen anderen Namen wählen. | `…_exists` |
| Die Vorschau oder Bestätigung ist abgelaufen. | Die Vorschau neu erstellen und dann bestätigen. | `…_expired` |
| Eine Gebühr ist ungültig. | Die Gebühr prüfen und korrigieren. | `…_fee_invalid` |
| Das Format einer Angabe oder Datei ist ungültig. | Angabe oder Datei prüfen und korrigieren. | `…_format_invalid` |
| Der Buchungsstand hat sich inzwischen geändert. | Die Ansicht neu laden und den Schritt wiederholen. | `…_generation_conflict` |
| Die Gruppe ist stillgelegt. | Eine aktive Gruppe wählen. | `…_group_inactive` |
| Die Kopfzeile der Datei passt nicht zum erwarteten Aufbau. | Die passende Datei oder Vorlage wählen. | `…_header_drift` |
| Die Kopfzeile der Datei passt nicht zum erwarteten Aufbau. | Die passende Datei oder Vorlage wählen. | `…_header_invalid` |
| Diese Bestätigung wurde schon mit anderem Inhalt verwendet. | Eine neue Vorschau erstellen und bestätigen. | `…_idempotency_conflict` |
| Die Funktion ist ausgeschaltet. | Sie in den Einstellungen einschalten, falls gewünscht. | `…_inactive` |
| Die Angaben sind noch unvollständig. | Die fehlenden Teile ergänzen, dann erneut versuchen. | `…_incomplete` |
| Eine Angabe ist ungültig. | Die Felder prüfen und korrigieren. | `…_input_invalid` |
| Bestand oder Menge reicht nicht aus. | Menge und Datum prüfen; fehlt eine frühere Buchung, diese zuerst erfassen. | `…_insufficient` |
| Die Abschottung fremder Plugins ist auf diesem System nicht möglich (Linux ab Kernel 6.2 mit Landlock 3 nötig). | Das System aktualisieren; bis dahin laufen fremde Plugins nicht. | `…_isolation_unavailable` |
| Der Schlüsselbund ist nicht erreichbar oder nicht eingerichtet. | Den Schlüsselbund der Arbeitsumgebung entsperren, dann erneut versuchen. | `…_keyring_unavailable` |
| Die Bezeichnung ist ungültig. | Eine andere Bezeichnung wählen. | `…_label_invalid` |
| Eine Grenze ist überschritten. | Weniger auf einmal verarbeiten. | `…_limit` |
| Gerade läuft ein anderer Vorgang, etwa „Alles aktualisieren“ oder ein Backup. | Warten, bis er beendet ist, dann erneut versuchen. | `…_lock_unavailable` |
| Portelyra ist mit dem Passwort gesperrt. | Zuerst entsperren, dann erneut versuchen. | `…_locked` |
| Angaben passen nicht zueinander. | Die Eingaben prüfen; nach einer Änderung an anderer Stelle die Ansicht neu laden. | `…_mismatch` |
| Eine benötigte Angabe oder Datei fehlt. | Die Angaben ergänzen oder die Datei erneut wählen. | `…_missing` |
| Der Name ist ungültig. | Einen anderen Namen wählen. | `…_name_invalid` |
| Das Ziel ist nicht leer. | Ein leeres Ziel wählen oder den Inhalt zuerst entfernen. | `…_not_empty` |
| Der Eintrag wurde nicht gefunden. | Die Ansicht neu laden; der Eintrag wurde vielleicht inzwischen geändert. | `…_not_found` |
| Die Voraussetzungen sind noch nicht erfüllt. | Die vorherigen Schritte abschließen, dann erneut versuchen. | `…_not_ready` |
| Das Datum liegt außerhalb des Zeitraums. | Datum oder Zeitraum prüfen. | `…_outside_period` |
| Zeiträume überschneiden sich. | Die Zeiträume prüfen. | `…_overlap` |
| Das Passwort ist falsch. | Das Passwort erneut eingeben. | `…_password_invalid` |
| Ein vorheriger Schritt ist noch offen. | Ihn abschließen, dann erneut versuchen. | `…_pending` |
| Der Zeitraum ist ungültig. | Anfang und Ende prüfen. | `…_period_invalid` |
| Das gewählte Portfolio ist nicht gültig. | Das Portfolio neu wählen; nach Änderungen die Ansicht neu laden. | `…_portfolio_invalid` |
| Der Buchungsstand hat sich inzwischen geändert. | Die Ansicht neu laden und den Schritt wiederholen. | `…_predecessor_conflict` |
| Die Vorschau fehlt oder ist nicht mehr aktuell. | Die Vorschau neu erstellen. | `…_preview_changed` |
| Die Vorschau fehlt oder ist nicht mehr aktuell. | Die Vorschau neu erstellen. | `…_preview_invalid` |
| Die Vorschau fehlt oder ist nicht mehr aktuell. | Die Vorschau neu erstellen. | `…_preview_missing` |
| Die Vorschau fehlt oder ist nicht mehr aktuell. | Die Vorschau neu erstellen. | `…_preview_required` |
| Die Vorschau fehlt oder ist nicht mehr aktuell. | Die Vorschau neu erstellen. | `…_preview_stale` |
| Ein Kurs oder Preis ist ungültig. | Den Wert prüfen und korrigieren. | `…_price_invalid` |
| Der Abruf beim Kursanbieter ist gescheitert. | Später erneut versuchen. | `…_provider_call_failed` |
| Eine Menge ist ungültig. | Die Menge prüfen und korrigieren. | `…_quantity_invalid` |
| Der Zeitraum ist ungültig. | Anfang und Ende prüfen. | `…_range_invalid` |
| Der geprüfte Saldo passt nicht zu den Buchungen des Zeitraums. | Saldo laut Auszug und Buchungen prüfen; meist fehlt eine Buchung. | `…_reconciliation_mismatch` |
| Es gibt keinen passenden unterbrochenen Vorgang zum Wiederaufnehmen. | Die Liste der unterbrochenen Vorgänge neu laden. | `…_recovery_missing` |
| Ein unterbrochener Vorgang muss zuerst abgeglichen werden. | Den unterbrochenen Vorgang wieder aufnehmen; die Karte zeigt ihn an. Danach erneut versuchen. | `…_recovery_required` |
| Die Angabe wurde abgewiesen. | Die Angaben prüfen und korrigieren. | `…_rejected` |
| Diese Bestätigung wurde schon verwendet. | Für einen weiteren Schritt eine neue Vorschau erstellen. | `…_replay` |
| Diese Bestätigung wurde schon mit anderem Inhalt verwendet. | Eine neue Vorschau erstellen und bestätigen. | `…_replay_conflict` |
| Eine Pflichtangabe fehlt. | Die fehlenden Angaben ergänzen. | `…_required` |
| Der Kursanbieter hat unerwartet geantwortet. | Später erneut versuchen. | `…_response_invalid` |
| Es gibt keinen unterbrochenen Vorgang zum Fortsetzen. | Den Vorgang neu beginnen. | `…_restart_unavailable` |
| Der Eintrag wurde inzwischen geändert. | Die Ansicht neu laden und den Schritt wiederholen. | `…_revision_conflict` |
| Dieser Kursanbieter ist für den täglichen Zeitlauf nicht freigegeben. | Die Freigabe für den Zeitlauf beim Kursanbieter erteilen oder von Hand abrufen. | `…_scheduled_disabled` |
| Die Einteilung ist stillgelegt. | Eine aktive Einteilung wählen. | `…_scheme_inactive` |
| Die Auswahl gehört zu einem anderen Stand als die Ansicht. | Die Ansicht neu laden und erneut wählen. | `…_scope_mismatch` |
| Die Auswahl ist nicht mehr gültig. | Neu auswählen. | `…_selection_invalid` |
| Portelyra läuft schon, oder ein anderer Vorgang ist aktiv. | Den anderen Vorgang beenden oder abwarten, dann erneut versuchen. | `…_session_conflict` |
| Die Quelle hat den Abruf abgewiesen, etwa wegen zu vieler Abrufe. | Etwas später erneut abrufen. | `…_source_rejected` |
| Die Daten haben sich inzwischen geändert. | Die Ansicht neu laden und den Schritt wiederholen. | `…_stale` |
| Der aktuelle Zustand erlaubt diesen Schritt nicht mehr. | Die Ansicht neu laden und den Schritt wiederholen. | `…_state_conflict` |
| Der Eintrag wurde inzwischen ersetzt. | Die Ansicht neu laden. | `…_superseded` |
| Der Buchungsstand hat sich inzwischen geändert. | Die Ansicht neu laden und den Schritt wiederholen. | `…_supersession_conflict` |
| Das Symbol ist ungültig. | Das Symbol beim Kursanbieter prüfen. | `…_symbol_invalid` |
| Verknüpfungen (Symlinks) werden aus Sicherheitsgründen nicht gelesen. | Die Datei selbst wählen. | `…_symlink_rejected` |
| Das gewählte Ziel ist nicht gültig. | Ein anderes Ziel wählen. | `…_target_invalid` |
| Datum oder Uhrzeit ist ungültig. | Datum und Uhrzeit prüfen und korrigieren. | `…_time_invalid` |
| Die Zeit für den Schritt ist abgelaufen. | Später erneut versuchen. | `…_timeout` |
| Die Zeitzone ist ungültig. | Die Zeitzone prüfen. | `…_timezone_invalid` |
| Der Kursanbieter meldet eine andere Börsenzeitzone als die Notierung. | Die Kurszuordnung prüfen (Symbol und Börse). | `…_timezone_mismatch` |
| Die Datei ist zu groß. | Eine kleinere Datei wählen. | `…_too_large` |
| Eine Buchung hat eine Form, die dieser Bericht noch nicht verarbeitet. | Bitte melden, welche Buchung betroffen ist. | `…_transaction_profile_unsupported` |
| Der Kursanbieter war nicht erreichbar. | Die Netzverbindung prüfen und später erneut versuchen. | `…_transport_failed` |
| Ein benötigter Dienst oder Stand ist gerade nicht verfügbar. | Später erneut versuchen; bleibt der Fehler, bitte melden. | `…_unavailable` |
| Der Eintrag ist unbekannt. | Die Ansicht neu laden; der Eintrag wurde vielleicht inzwischen geändert. | `…_unknown` |
| Das wird nicht unterstützt. | Eine unterstützte Variante wählen. | `…_unsupported` |
| Eine Angabe ist ungültig. | Die Felder prüfen und korrigieren. | `…_value_invalid` |
| Das Speichern ist gescheitert. | Freien Speicherplatz prüfen, dann erneut versuchen. | `…_write_failed` |
| Das Jahr ist ungültig. | Ein vorhandenes Jahr wählen. | `…_year_invalid` |


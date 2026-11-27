# Runtime Context Contract v1

Status: **Accepted – synthetic, owner-only product Desktop and externally verified Server Session projection**

## Binding

Der Desktop Adapter erzeugt intern:

- `runtime_mode=desktop_demo`;
- `tenant_id=local`;
- `user_id=demo_user`;
- explizite `data_space_id` mit Präfix `sbx_`;
- eine rollenabhängige, interne Actor-ID;
- einen absoluten vertrauenswürdigen Data Root.

Für private lokale Migrationen existiert zusätzlich `desktop_private` mit expliziten opaque Tenant/User/Sandbox-IDs, `desktop_owner`, festem Actor `desktop_owner` und `trusted_source=locally_confirmed_private_context`. ADR-096 ergänzt davon getrennt `desktop_product`: genau eine owner-only lokale Registry hält zufällig erzeugte opaque Tenant-/User-/Data-Space-IDs und ein getrenntes sichtbares Label; der Context ist fest `desktop_owner` und `trusted_source=owner_only_desktop_registry`. Keine ID wird aus Pfad, Browser, Label oder Demo-Default abgeleitet.

Tenant, User, Data Space, Rolle oder Root werden nicht aus Browserparametern übernommen. Additiv erzeugt ausschließlich ADR-095s Identity-Gateway aus einer aktuell autorisierten Server Session `runtime_mode=server`, `trusted_source=verified_server_session`, denselben opaque Context und den serverseitigen Actor. Browser-/CSV-/Pluginwerte können keinen solchen Kontext konstruieren.

## Isolation

Der Datenraum liegt ausschließlich unter:

```text
<data-root>/<tenant>/<user>/<data-space>/
```

Alle Segmente sind validierte opaque IDs. Traversal, relative Roots und Symlinks werden fail-closed abgelehnt. Canonical Store und Artifact-Areas werden nur aus diesem Kontext abgeleitet.

## Rollen

- `desktop_owner`: Data-App-Commands;
- `viewer`: Cockpit Latest Reader;
- `tax_viewer`: Tax Latest Reader;
- `market_worker`: erzeugt ausschließlich den fest definierten completed Demo-Market-Input;
- `portfolio_worker`: Portfolio Snapshot Writer;
- `tax_worker`: Tax Report Writer.

Ein Rollenwechsel erzeugt ausschließlich im Demo-Modus einen neuen Kontext mit identischer Tenant/User/Data-Space-Bindung und einer rollenfesten Actor-ID. Private und Product Desktop-Contexts sind absichtlich auf `desktop_owner` beschränkt. Ein Server-Kontext wird nach Capability-Prüfung nur als `desktop_owner`, `viewer` oder `tax_viewer` projiziert; `runtime_context_as()` darf ihn nicht umrollen oder zu einem Worker erheben. Worker erhalten ausschließlich separat signierte, einmalig konsumierte Job-Bindings.

## Datenschutz und Scope

Der Context-Fingerprint enthält nur interne IDs und keine Pfade. Der Demo-Modus akzeptiert ausschließlich synthetische Daten. Der Product-Modus bleibt außerhalb des Repositorys, startet über den festen Loopback-Launcher und erzeugt beim App-Start weder Store noch Domain Write. Der private Desktop-Modus bindet nur bereits lokal bestätigte opaque IDs und erteilt selbst keine Quell-, Provider- oder Schreibberechtigung. Provider, Push und Deployment bleiben ausgeschlossen. Der Server-Modus aktiviert weder einen Live-IdP noch Mail, Secrets, Proxy oder Serverkonfiguration; er ist ausschließlich die geprüfte Runtime-Projektion einer extern verifizierten Session.

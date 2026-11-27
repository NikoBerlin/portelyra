# Desktop Release and Local Safety v1

Status: **Release Candidate – synthetic gate required before private acceptance**

This contract defines the owner-only Linux Desktop release boundary for:

- quiescent complete-Data-Space backup;
- independent integrity validation;
- manifest-bound restore into a separate absent or explicitly empty Product home;
- versioned local runtime upgrade and rollback without Domain-data mutation, including self-bound validation of an older complete source inventory;
- reproducible tracked-source release archives with complete recursive local Python/R source closure;
- launch-session exclusion and one-use URL authorization;
- backup/restore of ADR-144's immutable ActivityDraft writer barrier and ADR-145's additive capability marker while advisory lock inodes remain excluded;
- rollback rejection when a Product writer barrier requires a capability absent from the target release;
- a private local acceptance result containing only `pass`, or `fail` plus one registered redacted code;
- backup size and content in the status line of `backup` and `backup-check` (creation time, product version, entry, file and byte counts; #438);
- `backup-prune` (#438): keeps the newest `keep` bundles of one Data Space that pass full validation, never counts or removes an invalid bundle, removes only older bundles of the same Data Space and only when `keep` valid ones exist; without a plan fingerprint it only plans, with the fingerprint of exactly that plan and `PRUNE_OWNER_BACKUPS` it removes; its output carries counts, times and sizes, never paths or names.
- Release signature (#486 step 3): once `contracts/plugin-signing/v1/allowed_signers` carries a key,
  `release_build` signs `release-manifest.json` (namespace `portelyra-release`) through the project's own signing agent, which has every signature
  confirmed in a window; the signature travels as `release-manifest.json.sig` inside the
  archive. `release_check` reports `signature` (`valid` or `not_required`) against the trust list of the checking project.
- `update --archive` (`release_update_stage` + upgrade): runs only from the installed release; copies the archive into an owner-only
  staging directory, checks structure, checksums and signature against the trust list of the INSTALLED release (empty: not required;
  with a key: required without exception) and unpacks only the manifest entries before the regular upgrade. `upgrade` from a directory
  remains the development path and executes that directory's code without a signature check.

Normative files are the contract, JSON Schemas and CSV matrices in this directory. The fixed implementation is `workers/reference/desktop_release_v1.py`, with the shared closure gate in `workers/reference/desktop_release_source_closure_v1.py`; it is reached from `scripts/desktop_release.py` and the single `scripts/portelyra_desktop.R` launcher. Tests use invented values and automatically removed owner-only temporary roots only.

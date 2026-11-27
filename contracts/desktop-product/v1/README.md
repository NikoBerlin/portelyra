# Desktop Product Runtime and Onboarding v1

Status: **Accepted – local Linux single-user product boundary**

ADR-161 adds a separate synthetic-only Statement review card to Data. It can run only the registered invented Valid/Adversarial fixtures of the six still-disabled ADR-158 adapters and displays every Candidate/Diagnostic row plus mapping requirements. It accepts no private source and grants no Mapping, ActivityDraft, schema-401, Cash, UAT or activation authority.

ADR-157 adds an owner-driven staged Daily Market History path to the Asset Center. It provides separate fetch and publication confirmations, immutable query-only canonical Mapping revalidation, owner-local sealed staging, exact table/plot review and explicit recovery. Synthetic tests use invented transport bytes only; this source integration does not authorize a real external price fetch, productive publication, release or Runtime activation.

This contract replaces no synthetic Desktop Demo contract. It adds one product launcher, an owner-only opaque Runtime registry, a read-only preflight, explicit local package installation and an empty canonical Data-Space bootstrap. Candidate inventory is current-version strict, while a complete installed older slot is validated against its own integrity-bound registry before a strictly newer confirmed Upgrade. The pre-RC7 eight-command onboarding plan remains compatibility-tested but is unavailable in the Product UI; first-user masters use Catalog Commands/CSV, Non-Cash history uses schema-401 Asset Activity and optional Cash uses schema-2900 Cash Coverage. ADR-149 adds only a browser-local manual selected/all presentation scope over existing Activity read tables; it does not add a Product writer, calculation or batch Activity command.

Normative rules are in `desktop-product-contract.md`. `scripts/portelyra_desktop.R` is the only supported product entry in v1. Data, Cockpit, Tax and Analysis remain separate capability domains; v1 starts only the Data onboarding app. The four-app calculation workflow follows in issue #108.

The installed source snapshot includes the explicitly invented Product review fixtures under `fixtures/product/legacy-per-asset-review-v1/`; they are test/demo input only and never grant Legacy or private-path authority. Schema-401 Product authority is defined additively by `contracts/desktop-product-asset-activity/v1/`.

No file in this contract authorizes Server/OIDC activation, unattended Provider networking, private-data reads, deployment, mail, alarms or cron. Each real external price fetch and each productive Market publication remains a separately authorized owner operation under the narrower Market History Review contract.

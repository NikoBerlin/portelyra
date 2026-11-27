# Desktop Workflow v1

Provider-free Product Desktop composition for issue #108 and ADR-097.

The Data Run Center is the only UI allowed to create canonical Commands or start the fixed Workflow Worker. Data, Cockpit, Tax and Analysis read one atomically published `desktop_workflow_v1` revision; the three display apps cannot open SQL, start Workers or write. Immutable running checkpoints expose safe Stage progress while retaining prior usable values stale.

Normative files include the workflow contract, Plan/Confirmation/Job/Artifact/Browser schemas, stage and capability matrices, failure codes, state machine and source fingerprints. Tests use owner-only invented roots only.

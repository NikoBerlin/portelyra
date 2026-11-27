# Single correction/void public preview v3

The immutable writer and receipt remain the existing v1 authority. This public
presentation version corrects the meaning of `affected_fifo_world_count`: it is
the union of changed before/after portfolio × asset FIFO worlds, so a world that
vanishes after void still counts as affected.

`after_state=no_remaining_events` is emitted only when every changed world has no
remaining effective event. Otherwise it is `present`. The field is presentation
evidence bound into the native plan fingerprint; it does not add write authority.
Batch previews continue to use v2 with per-world `after_state` entries.

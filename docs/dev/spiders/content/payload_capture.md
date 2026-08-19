# spiders/content/payload_capture.py

## module

One truncate-and-hash primitive for anything stored content-addressed.

It exists so the capture paths cannot drift on how a payload becomes a stored
row. `truncate_and_hash` returns `(excerpt, byte_length, sha256_hex)`, and each
of the three carries a distinct fact:

- **`excerpt`** is what actually gets stored, bounded by `cap_bytes` (8KB for
  network bodies). Bounded in **UTF-8 bytes**, not characters, because the cap
  exists to bound storage.
- **`byte_length`** is the *original* size, so "this was huge" survives even
  when the content does not. A 400KB response truncated to 8KB still reports
  400KB, which is the difference between a document saying "large payload" and
  a document quietly describing an 8KB one.
- **`sha256_hex`** hashes the **full** text, not the excerpt. Two payloads
  identical for their first 8KB and different afterwards get different hashes,
  so content-addressing stays honest at the boundary where truncation would
  otherwise collapse them.

`Payload.hash` is the primary key those hashes land on, which is what makes a
body observed twenty times cost one row.

**This function has no opinion on redaction.** Text arrives already redacted by
`redaction.py` if it needed to be; this only bounds size and computes identity.
Keeping the two separate matters because the hash must be of the text that gets
stored - hashing before redaction would key rows by content that no longer
exists anywhere.

It was originally written for stylesheet capture, which was retired with the
measurement pass, and had been computing hashes for network bodies that had no
table to receive them until `Payload` was wired up. See
`docs/dev/database/ladybug/schema.md`.

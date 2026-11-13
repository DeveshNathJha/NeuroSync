# Privacy and safety

NeuroSync handles video, audio and physiological signals of people who may be children
or otherwise vulnerable. This document explains what the software does to protect them,
and what it does **not** do, so nobody mistakes a prototype for a validated product.

## 1. Intended use

* **Intended:** a professional (therapist, researcher) keeps time-stamped observation notes of
  observable behaviour during a session they are running, and reviews them afterwards.
* **Not intended:** diagnosis, screening or assessment of any condition; continuous monitoring;
  use without the subject's (or guardian's) informed consent; decisions about a person without
  human review.

Software that claims to diagnose or assess a condition is regulated as a medical device in most
jurisdictions (e.g. CDSCO in India, FDA in the US). NeuroSync makes no such claim, and must not
be presented as doing so.

## 2. What the software enforces

| Principle | Implementation | Where |
|---|---|---|
| Consent before capture | A `Consent` record (pseudonymous subject id, who consented, who recorded, purpose, video-storage opt-in) is required to create a session. | `src/core/session.py`, `src/ui/consent.py` |
| Pseudonymisation | Subject ids are free text chosen by the professional; the form warns if an id looks like a name, e-mail or phone number. | `src/ui/helpers.py` |
| Purpose and time limitation | Sessions have an explicit start/stop and a hard maximum duration (`session.max_duration_min`); there is no background mode. | `src/core/session.py` |
| Human review | Every detection is `pending`; only `confirmed` events reach notes, history and exports. | `src/core/session.py`, `src/storage/store.py`, `src/reporting/` |
| Data minimisation | Uploaded videos are deleted after analysis unless storage was consented to and allowed by settings. Live video is never written to disk. | `src/ui/video_analysis.py`, `src/ui/helpers.py` |
| Encryption at rest | Session files and the session index are encrypted with Fernet; the key is generated per installation in the data directory and can be rotated. | `src/storage/keystore.py`, `src/storage/store.py` |
| Key outside the code | The key store refuses any key path inside the project folder, so a key can't be committed by accident; CI also fails if a `.key`/`.enc` file is tracked. | `src/storage/keystore.py`, `.github/workflows/ci.yml` |
| Erasure and portability | Delete a session, delete all data of a subject, export a subject's data as JSON. | `src/storage/store.py`, `src/ui/data_management.py` |
| Accountability | Append-only audit log of saves, views, exports and deletions with a SHA-256 hash chain; integrity check in the UI. Logs contain ids and actions only. | `src/storage/audit.py` |
| Retention | Sessions older than `storage.retention_days` can be purged. | `src/storage/store.py` |
| Non-diagnostic wording | Generated notes pass through a guard that removes diagnostic or interpretive statements, and every note and PDF page carries the disclaimer. | `src/reporting/guard.py` |
| No cloud | All processing (including the optional LLM) runs on the local machine; nothing is uploaded. | whole codebase |

## 3. What a real deployment would still need

1. **Ethics approval and a clinical partner** for any pilot, with an informed-consent process
   designed with them (children: verifiable parental consent; India's DPDP Act 2023 requires it).
2. **Validation** of every detector on consented recordings annotated by experts, reported per
   subgroup (age, skin tone, lighting), especially for contactless heart rate.
3. **Access control:** user accounts and roles. Today anyone with access to the computer and the
   OS account can open the app.
4. **Key management:** a passphrase or OS keychain/HSM instead of a key file next to the data.
5. **Secure deletion guarantees** on the storage medium, and backups that respect erasure.
6. **A data-protection impact assessment** and documented data-processing agreements.
7. **Accessibility and respectful language** reviewed with the communities concerned. Many
   behaviours NeuroSync can log, such as repetitive movements, are not problems to be "fixed".

## 4. Reporting a concern

Please open an issue on the repository for any privacy or safety concern.

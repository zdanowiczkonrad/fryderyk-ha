# AISDLC — fryderyk-ha customization

This project follows the generic **`aisdlc`** skill (plugin `aisdlc`, marketplace
`zdanowicz-dev/claude-skills`) for *how* work is done — the loop, the PR flow, the
escalation categories, and the usage discipline. **Read that skill for the method.**
This file only records what's specific to **fryderyk-ha**. Keep it thin; do not
re-document the generic loop (that lives in the skill and must not drift).

Install the bar once per machine:

```
/plugin marketplace add zdanowicz-dev/claude-skills
/plugin install aisdlc@zdanowicz-dev
```

## Customization contract (the slots the skill expects)

| Slot | This project |
| --- | --- |
| **Roadmap location** | `docs/ROADMAP.md` |
| **Detail docs** | `docs/project/` (one file per theme; scope, decisions, retro log) |
| **Check command** | `./scripts/check.sh` (ruff + parser tests + HA tests via pytest-homeassistant-custom-component); CI runs the same via `.github/workflows/check.yml` |
| **Deploy path** | Not set up yet (see roadmap). Target: tag a release → HACS update in the user's HA; until then manual copy of `custom_components/fryderyk` into the HA config dir + restart |
| **Conventions** | Branches `feat/` `fix/` `docs/` `infra/`; conventional commits; commit trailer per the session's attribution reminder |

## Escalation targets (concrete instances of the skill's §5 categories)

Do **not** proceed autonomously — stop and ask — when a change touches any of these:

- **Uptime / availability**: the user's running Home Assistant instance (installing, updating or restarting it, editing its config).
- **Irreplaceable data**: `.env` (real school credentials, never committed or printed); the HA config entry holding the password.
- **Destructive / irreversible**: anything that changes state on the school's Fryderyk account. Opening a message marks it read; sending, deleting or tagging messages. The integration and tests must stay read-only, apart from the explicit CLI `message`/`-b` commands.
- **Material cost / external**: creating or publishing the GitHub repo, HACS listing, raising the polling frequency (load on the school's server; keep ≥15 min).

Everything else → autonomous PR flow, auto-merge once CI is green.

## Notes

- There is no API. The integration scrapes the same HTML fragments the site's JS loads
  (`/plans/mine/<date>`, `/lessons/details/...`, `/messages/get-messages/<folder>/<page>`,
  `/announcements/get-announcements/<page>`, `/app/*-count/`). `custom_components/fryderyk/parsing.py`
  is the single parser shared by the integration, CLI and tests.
- Test fixtures are **synthetic** copies of real markup. Never commit real pages; they contain
  children's names and teacher data.
- Announcement and substitution markup has not been seen live yet; parsers for them are inferred.

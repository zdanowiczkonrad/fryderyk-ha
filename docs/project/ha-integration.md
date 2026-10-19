# Home Assistant integration

## Scope

Read-only integration for the Fryderyk e-journal. It provides a lesson calendar, sensors for the next lesson,
lessons today, cancelled lessons, unread and latest message, and announcements, plus bus events
for new cancellations and new messages. UI config flow with reauth; options for weeks ahead and polling interval.

## Decisions

- **Scraping, not an API**: Fryderyk has no public API. We reuse the endpoints the site's own JS calls.
- **Never open message bodies** from HA: the server marks them read. Only list data is used.
- **Shared parser** (`parsing.py`, no HA imports) between the CLI, the integration and the tests, so they can't drift.
- **Dedicated aiohttp session** per entry, so the login cookie stays out of HA's shared session. Re-login is transparent when the session expires.
- **Lesson details cached** per lesson URL; cancelled and substituted lessons are refetched every poll.
- **Default poll 30 min, minimum 15**, to be polite to the school's server.

## Retro log

### 2026-10-18: v0.1 built
- **Done:** integration (`custom_components/fryderyk`), CLI refactored onto the shared parser, synthetic fixtures, 14 tests, `scripts/check.sh`, HACS metadata, README. Not committed; there is no remote yet.
- **Verified:** `./scripts/check.sh` green (ruff, 7 parser tests and 7 HA tests on HA 2026.2.3 via PHCC 0.13.316). Live read-only smoke test of the async client against the real site: wrong password rejected, 2 real cancellations found, counts match.
- **Usage:** one moderate session.
- **Learned:** a failed login re-renders the form, so success is detected from the HTML, not the URL. The inbox list endpoint is `/messages/get-messages/inbox/<page>`; the JS variant with `/undefined/` is a 404.
- **Next:** item 3 (repo + CI) and item 4 (deploy). Both need the user's go-ahead, plus the HA host and install method (HACS vs manual).

### 2026-10-18: local repo
- **Done:** git repo initialised on `main` with the first commit; `.github/workflows/check.yml` runs `scripts/check.sh` once a remote exists.
- **Verified:** `./scripts/check.sh` green before the commit; `.env` is ignored and not tracked.
- **Learned:** the user wants to add the remote (`origin`) themselves, later.
- **Next:** item 4 (deploy). It needs the HA host and install method (HACS needs the remote; until then, a manual copy).

### 2026-10-19: published
- **Done:** public repo `zdanowiczkonrad/fryderyk-ha` created and `main` pushed (user asked). Before pushing, the example school host was replaced with a placeholder and the manifest links were pointed at the new repo.
- **Verified:** scanned all history for the password, the child's login, teacher names and the school host: none found. First CI run green.
- **Learned:** keep real school or person identifiers out of examples; the repo is public.
- **Next:** tag `v0.1.0` (a GitHub release) so HACS shows a version; then item 4 (deploy to HA via HACS custom repository).

### 2026-10-19: release v1.0.0
- **Done:** manifest version bumped to 1.0.0; tagged `v1.0.0` and published a GitHub release (the user chose 1.0.0 over 0.1.0).
- **Next:** item 4. Install via HACS custom repository on the home HA and verify the live entities.

# Engineering Operations Guide

This guide is for the Ansible Community Team engineers who run the event provisioning tooling. It covers every operation from initial setup to creating events, syncing content, and adding new cities and organisers.

---

## Prerequisites

### System requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Git

### Environment variables

Set these before running any script:

```bash
export PRETIX_URL="https://pretix.example.com"       # Non-local Pretix URLs must use HTTPS (default: http://localhost:8000)
export PRETIX_API_TOKEN="your-pretix-api-token"       # Required — Pretix API authentication
export DISCOURSE_API_KEY="your-discourse-api-key"     # Required — Discourse API authentication
```

`PRETIX_API_TOKEN` and `DISCOURSE_API_KEY` are required. Scripts will exit immediately if they are missing.

The Discourse URL (`https://forum.ansible.com`) and API user (`system`) are hardcoded — they are the same for all deployments.

### Installation (this tooling)

```bash
git clone <repo-url>
cd discourse-pretix-luma
uv sync --group dev
```

### Verify the installation

```bash
uv run pytest tests/ -v          # 56+ tests should pass
uv run pyright scripts/          # 0 errors expected
bash lint.sh                     # All checks should pass
```

---

## Discourse Theme Component: Event JSON-LD

A theme component injects `schema.org/Event` JSON-LD structured data on forum topics that have a Discourse Event widget. This enables Google Rich Results (event cards in search).

### Installation (one-time, Discourse admin)

1. Go to `forum.ansible.com` → Admin → Appearance → Themes → Components
2. Click **Install** → **Create New**
3. Name it **"Event JSON-LD Structured Data"**
4. In the component editor, go to **Common** → click **`</head>`**
5. Paste the entire contents of `discourse-theme/event-jsonld/common/head_tag.html`
6. Click **Save**
7. Go back to Appearance → Themes → select your active theme
8. Under **Theme Components**, click **Add** and select "Event JSON-LD Structured Data"
9. Click **Save**

No rebuild is needed — theme components take effect immediately on save. Discourse does not require a `Rebuild HTML` step for theme changes (unlike Discourse plugins which require a container rebuild).

### What it does

- Detects the `.discourse-post-event` div (rendered server-side by the Events plugin)
- Parses `data-start`, `data-end`, `data-timezone`, `data-name` attributes
- Injects a `<script type="application/ld+json">` block with schema.org/Event markup
- Sets the forum topic URL as the canonical event URL
- Marks events as free (`isAccessibleForFree: true`)
- Cleans up the JSON-LD when navigating away from event topics

### Testing

**Step 1: Browser test (immediate)**

1. Navigate to any event topic on the forum (e.g., an Ansible London meetup)
2. Open browser DevTools (F12) → Console
3. Run: `document.getElementById('ansible-event-jsonld')?.textContent`
4. You should see a JSON object with `"@type": "Event"`, `"name"`, `"startDate"`, etc.
5. Navigate to a non-event topic and run the same command — should return `undefined`

**Step 2: Structured data validation**

1. Open [Google's Rich Results Test](https://search.google.com/test/rich-results)
2. Enter a forum event topic URL (use **URL** input, not code input — URL mode renders JavaScript)
3. Wait for the tool to render the page
4. Check that **"Event"** appears in the "Detected structured data" section
5. Review any warnings (e.g., missing `location` — expected, see Limitations)

**Step 3: Schema validator (optional, more detailed)**

1. Open [Schema Markup Validator](https://validator.schema.org/)
2. Enter the same event topic URL
3. Verify the Event type is detected with correct `startDate` and `name`

**If the test does NOT detect the Event structured data:**
- Confirm the theme component is saved and added to the active theme
- Confirm the page has a `.discourse-post-event` div (view page source, search for `discourse-post-event`)
- Check the browser console for JavaScript errors
- Try a hard refresh (Ctrl+Shift+R) to bypass cached theme assets

### Limitations

- **No `location` field** — the event widget doesn't carry structured venue data. Google requires a physical address for the event carousel. Consider adding venue info to the JSON-LD if a structured venue field is added to the Events plugin in future.
- **JavaScript-dependent** — relies on Googlebot rendering JS (which it does, but with potential delay). An upstream PR to the Events plugin for server-side JSON-LD would be more reliable.

---

## Pretix Server Configuration

These steps are performed once on the Pretix server, not by the CLI tooling.

### Required pip packages

Install in the Pretix Docker image or virtualenv:

```bash
pip install pretix-passbook
```

| Package | Purpose |
|---|---|
| `pretix-passbook` | Apple Wallet (.pkpass) and Google Wallet pass generation for attendees |

### pretix.cfg (SSO plugin)

The `pretix-discourse-auth` plugin reads from `pretix.cfg`. Add this section:

```ini
[discourse_auth]
url = https://forum.ansible.com
sso_secret = <shared-secret-min-32-chars>
api_key = <discourse-admin-api-key>
api_username = system
organizer = ansible-meetups
api_timeout = 10
```

| Key | Notes |
|---|---|
| `sso_secret` | Must match the DiscourseConnect secret in Discourse admin. Minimum 32 characters. |
| `api_key` | Discourse Admin API key with "All Users" scope. |
| `organizer` | Pretix organizer slug — must match `ORGANIZER_SLUG` in `ansible_events_lib.py`. |

The plugin hardcodes `meetup-staff` and `meetup-organisers-{city}` as the only groups that grant Pretix privileges. DiscourseConnect always requests 2FA; the signed response must positively attest that the challenge was completed for staff and organisers. The Discourse Admin API key is required for every login to verify account security status. Missing or invalid API credentials deny login.

Restart Pretix after any `pretix.cfg` changes (config is loaded at import time).

### Footer links and legal pages

Code of Conduct and Privacy Policy links are set automatically by `provision_environment.py` via the organizer-level `imprint_url` and `privacy_url` settings. These appear in the footer of every event page — no additional plugins needed.

The organizer homepage (`/ansible-meetups/`) is also configured automatically with a welcome message linking to the forum.

### Passbook configuration (Apple/Google Wallet)

After installing `pretix-passbook`, configure in Pretix admin → Organizer → Settings → Passbook:

- Upload an Apple Developer certificate (.p12 file) for signing .pkpass files
- Set the organisation name and pass style
- Enable the plugin on the event template (added to `TEMPLATE_PLUGINS` automatically)

Without the certificate, Apple Wallet passes won't generate. Google Wallet passes require a separate Google Pay API setup.

---

## Initial Setup

**Script:** `scripts/provision_environment.py`

This script reconciles the infrastructure in Discourse and Pretix to the configured desired state. It creates missing resources and updates existing groups, category permissions, template settings, and Pretix team permissions. It fails if API requests cannot complete; review the output and fix any error before relying on the resulting permissions.

### What it creates

**In Discourse:**

| Resource | Example | Purpose |
|----------|---------|---------|
| Staff group | `meetup-staff` | Grants Pretix staff access via SSO |
| Organiser group (per city) | `meetup-organisers-london` | Grants the city's scoped Pretix and category access |
| Attendee group (per city) | `meetup-attendee-london` | Hidden city subscriptions |
| Subcategory (per city) | `Events > London` | Regional forum category |

**In Pretix:**

| Resource | Example | Purpose |
|----------|---------|---------|
| Organizer settings | Contact email, UTC timezone | Global configuration |
| Meta property | `forum_topic_url` | Links events to forum topics |
| Template event | `ansible-meetup-template-v6` | Master template for cloning |
| RSVP item + quota | "RSVP" at $0.00, 100 capacity | Default ticket configuration |
| Team (per city) | `Ansible Meetup Organisers - London` | Scoped organiser access |

### How to run

```bash
uv run python scripts/provision_environment.py
```

### What to check after

1. Visit Discourse admin → Groups — verify `meetup-staff`, `meetup-organisers-{city}`, and `meetup-attendee-{city}` groups exist. Their visibility must be owners-only (level 4), members-only (level 2), and staff-only (level 3), respectively.
2. In Discourse admin → Settings, verify category group moderation is enabled. Visit each city subcategory and confirm only that city's `meetup-organisers-{city}` group is assigned as a category moderator. Event topics are created directly in that city subcategory.
3. Visit Pretix admin → Events — verify the template event `ansible-meetup-template-v6` exists (not published).
4. Visit Pretix admin → Teams — verify `Ansible Meetup Organisers - {City}` teams exist.

### When to re-run

- After adding a new city to the `CITIES` registry in `ansible_events_lib.py`.
- After any change to template settings (checkout rules, plugins, etc.).
- As a health check — re-running confirms everything is in place.

---

## Creating an Event

**Script:** `scripts/create_event.py`

This is the primary workflow. It creates a complete meetup: forum topic, Pretix event, social media copy.

### Prerequisites

1. `provision_environment.py` has been run at least once.
2. The organiser has a Discourse account.
3. The organiser is a member of the `meetup-organisers-{city}` Discourse group.

### Command

```bash
uv run python scripts/create_event.py \
    --city london \
    --date "2026-11-15T18:00:00" \
    --capacity 50 \
    --organiser gundalow
```

### Arguments

| Argument | Required | Format | Description |
|----------|----------|--------|-------------|
| `--city` | Yes | `^[a-z]+$` | Lowercase city name already present in the `CITIES` registry |
| `--date` | Yes | `YYYY-MM-DDTHH:MM:SS` | Event start time **in the city's local timezone** |
| `--capacity` | Yes | Integer | Maximum number of attendees |
| `--organiser` | Yes | Discourse username | Must exist and be in `meetup-organisers-{city}` group |

**Important:** `--date` is in the event's **local time**, not UTC. If the event is in London at 6pm, use `2026-11-15T18:00:00`. The script automatically uses the city's timezone from the registry.

### What happens (step by step)

1. **Validate** — Checks city syntax and registration, organiser exists and is in the exact `meetup-organisers-{city}` group, the template and team exist, and the target event is confirmed absent. API failures stop the operation.
2. **Create Discourse topic** — Posts a forum topic on behalf of the organiser with event details, agenda table, share section, and RSVP placeholder.
3. **Create Pretix event** — Clones the master template with the city's timezone, links to the forum topic.
4. **Update Discourse post** — Replaces placeholder URLs with the real Pretix RSVP link and share link.
5. **Sync to Pretix** — Copies the markdown content (below the `---` separator) to the Pretix frontpage.
6. **Set quota** — Adjusts venue capacity to the specified value.
7. **Publish** — Makes the Pretix event live.
8. **Assign team** — Adds the event to the city's organiser team (with pagination-safe read-modify-write).
9. **Social media copy** — Prints ready-to-paste text for X, Bluesky, Mastodon, LinkedIn, Reddit, and Hacker News.

### Example output

```
2026-10-05 14:30:00 - INFO - Validating organiser @gundalow...
2026-10-05 14:30:01 - INFO - Drafting initial forum post on behalf of @gundalow...
2026-10-05 14:30:02 - INFO - Forum post created: https://forum.ansible.com/t/ansible-meetup-london-november-2026/1234
2026-10-05 14:30:03 - INFO - Cloning Pretix event from 'ansible-meetup-template-v6'...
2026-10-05 14:30:04 - INFO - Pretix event created: https://pretix.example.com/ansible-meetups/london-nov-2026/
...
2026-10-05 14:30:08 - INFO - --- EVENT SUCCESSFULLY PROVISIONED ---

================================================================================
SOCIAL MEDIA COPY (ready to paste)
================================================================================
📱 X / TWITTER:
...
```

### If it fails partway through

The script verifies the city, organiser, template, team, and event state before creating resources. Pretix lookup failures stop the run; only a confirmed `404` means the event is absent. If Pretix event creation fails after the Discourse topic was created, the script attempts to delete the topic. If cleanup also fails, remove it manually before retrying.

---

## Syncing Content

**Script:** `scripts/pretix-sync-event.py`

When an organiser updates their forum post (e.g., adds speakers, changes venue), use this script to push the changes to the Pretix event page.

### Command

```bash
uv run python scripts/pretix-sync-event.py --slug london-nov-2026
```

### What it does

1. Fetches the Pretix event to find the linked forum topic URL.
2. Fetches the forum topic to get the first post ID.
3. Fetches the post's raw markdown via the Discourse API.
4. Strips the Discourse-specific `[event]` block (everything above the first `---` separator).
5. Updates the Pretix event title and frontpage with the clean markdown.

### When to use

- After an organiser edits the venue, agenda, or speaker list on the forum.
- Automated via cron for regular sync (future enhancement).

### Event slug format

Slugs follow the pattern `{city}-{mon}-{year}`, e.g., `london-nov-2026`, `barcelona-dec-2026`. Only lowercase letters, numbers, and hyphens are accepted.

---

## Adding a New City

### 1. Add to the CITIES registry

Edit `scripts/ansible_events_lib.py` and add a new `CityInfo` entry:

```python
CITIES: tuple[CityInfo, ...] = (
    CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London"),
    CityInfo(region="Europe", country="Spain", city="Barcelona", timezone="Europe/Madrid"),
    CityInfo(region="Europe", country="UK", city="FakeTown", timezone="Europe/London"),
    # Add new city:
    CityInfo(region="APAC", country="Japan", city="Tokyo", timezone="Asia/Tokyo"),
)
```

The `city` field is the display name; the CLI uses its lowercase slug (`tokyo`). Add the city to `CITIES` and deploy that code before running `create_event.py`. Unknown or unregistered city slugs are rejected; no fallback timezone is used.

Use [IANA timezone identifiers](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for the `timezone` field.

### 2. Run provisioning

```bash
uv run python scripts/provision_environment.py
```

This creates:
- Discourse groups: `meetup-organisers-tokyo`, `meetup-attendee-tokyo`
- Discourse subcategory: `Events > Tokyo`
- Pretix team: `Ansible Meetup Organisers - Tokyo`

### 3. Verify

```bash
# Check the team was created
uv run python -c "
from scripts.ansible_events_lib import get_city
city = get_city('tokyo')
print(f'City: {city.city}, TZ: {city.timezone}, Team: {city.team_name}, Organiser group: {city.organiser_group}')
"
```

### 4. Run tests

```bash
uv run pytest tests/ -v
```

The `TestCitiesRegistry` tests will automatically verify the new city has all required fields, a valid timezone, and no duplicate names.

---

## Adding a New Organiser

### 1. Add them to the Discourse group

In Discourse admin → Groups → `meetup-organisers-{city}` → Members → Add:

- Search for the user's Discourse username.
- Add them as a member.

### 2. Verify

```bash
uv run python -c "
from scripts.ansible_events_lib import discourse_user_in_group
print(discourse_user_in_group('newuser', 'meetup-organisers-london'))
"
```

Should print `True`.

### 3. Use them in event creation

```bash
uv run python scripts/create_event.py --city london --date "2026-12-01T18:00:00" --capacity 50 --organiser newuser
```

### 4. Pretix access

On the organiser's first login to Pretix via Discourse SSO, the auth plugin automatically:

- Creates their Pretix account (linked to their Discourse identity).
- Adds them to the `Ansible Meetup Organisers - London` Pretix team.
- Grants them `event.orders:read` and `event.orders:checkin` permissions for London events.

No manual Pretix configuration is needed.

---

## Migrating from Meetup Pro

When migrating attendees from a Meetup Pro city to the forum, create invite links that auto-add users to the right groups.

### Prerequisites

- The city must be provisioned (`provision_environment.py` has run).
- The `meetup-migrated-from-meetup-pro` group exists (created automatically by `provision_environment.py`).

### Creating invite links (manual — Discourse admin UI)

For each city being migrated, create **one invite link** in Discourse:

1. Go to `https://forum.ansible.com/u/{your-admin-username}/invited/pending`
2. Click **"Create Invite Link"**
3. Configure:
   - **Max uses:** 5,000
   - **Expire after:** Never
   - **Add to groups:** select both:
     - `meetup-attendee-{city}` (subscribes them to city event notifications)
     - `meetup-migrated-from-meetup-pro` (tracks who came from Meetup Pro)
4. Copy the invite link

**Do not add migrating attendees to `meetup-organisers-{city}`** — that group grants organiser permissions (Pretix dashboard, category moderator). Organisers are added individually after Community Engineering lead approval.

### Distributing invite links

Send the invite link to the Meetup Pro group members via:
- Meetup Pro's built-in messaging (before the group is deactivated)
- Email (if you have the contact list from the Meetup Pro export)
- The Meetup Pro group's description/announcement

### Tracking migration progress

The `meetup-migrated-from-meetup-pro` group tracks everyone who joined via a migration invite link. To check progress:

- Discourse admin → Groups → `meetup-migrated-from-meetup-pro` → Members
- Compare the member count against the original Meetup Pro group size

### Onboarding organisers (separate process)

Organiser migration is handled individually, not via invite links:

1. Contact the organiser directly
2. Ensure they create a forum account (or use the city invite link)
3. Add them to `meetup-organisers-{city}` manually after Community Engineering lead approval
4. Remind them to enable 2FA — they cannot access the Pretix dashboard without it

---

## Development

### Code quality checks

All three must pass before committing:

```bash
# Linting and formatting (auto-fixes where possible)
bash lint.sh

# Tests (56+ tests covering pure functions, URL building, config validation)
uv run pytest tests/ -v

# Static type checking (zero errors required)
uv run pyright scripts/
```

### Ruff rules enabled

`E` (pycodestyle), `F` (pyflakes), `B` (bugbear), `S` (bandit), `T20` (print), `DTZ` (datetimez), `UP` (pyupgrade), `SIM` (simplify), `G` (logging-format).

### Adding a test

Tests go in `tests/test_ansible_events_lib.py`, organised as classes:

```python
class TestNewFeature:
    def test_does_the_thing(self) -> None:
        assert some_function("input") == "expected"
```

---

## Troubleshooting

### "Pretix event already exists"

```
ERROR - Pretix event 'london-nov-2026' already exists. Aborting to prevent duplicates.
```

The event was already created (possibly from a previous run). If you need to recreate it, delete the existing event in Pretix admin first.

### "Discourse user does not exist"

```
ERROR - Discourse user 'nonexistent' does not exist.
```

Check the username spelling. Discourse usernames are case-insensitive but must match exactly (no leading/trailing spaces).

### "User not in group"

```
ERROR - User 'gundalow' is not in group 'meetup-organisers-london'. Add them to the group first.
```

Add the user to the group in Discourse admin → Groups → `meetup-organisers-london` → Members.

### API connection errors

```
ERROR - Pretix GET events connection error: [ConnectError]
```

Check that:
1. `PRETIX_URL` is correct and reachable, `DISCOURSE_API_KEY` is valid.
2. `PRETIX_API_TOKEN` and `DISCOURSE_API_KEY` are valid (not expired or revoked).
3. Your network allows outbound HTTPS connections to both services.

### Template not found

```
ERROR - Failed to create Pretix event.
```

If the clone fails, the template may not exist. Run `provision_environment.py` first.

### Missing environment variables

```
ERROR - Missing required environment variables: PRETIX_API_TOKEN, DISCOURSE_API_KEY
```

Set the required environment variables (see [Prerequisites](#prerequisites)).

---

## Quick Reference

### Scripts

| Script | Purpose | When to use |
|--------|---------|-------------|
| `provision_environment.py` | Create Discourse groups/categories and Pretix template/teams | Initial setup + new cities |
| `create_event.py` | Provision a complete meetup (forum + Pretix + social) | Each new event |
| `pretix-sync-event.py` | Sync forum content changes to Pretix | After organiser edits the post |

### Key constants (ansible_events_lib.py)

| Constant | Value | Purpose |
|----------|-------|---------|
| `ORGANIZER_SLUG` | `ansible-meetups` | Pretix organizer |
| `TEMPLATE_SLUG` | `ansible-meetup-template-v6` | Master template event |
| `ORGANISERS_GROUP_PREFIX` | `meetup-organisers` | Discourse group prefix for organisers |
| `STAFF_GROUP_NAME` | `meetup-staff` | Discourse group for Pretix staff access |
| `ORGANISER_TEAM_PREFIX` | `Ansible Meetup Organisers` | Pretix team name prefix |

### Event slug format

`{city}-{month}-{year}` — e.g., `london-nov-2026`, `new-york-jan-2027`

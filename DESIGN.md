# Architecture & Implementation Specification: Ansible Meetups Integration

This document outlines the objectives, core design decisions, and script inventory for the integration between Pretix (event management) and Discourse (Ansible Community Forum).

---

## 1. Core Objectives

* **Single Source of Truth:** Discourse handles all identity, authentication, group membership, moderation status, and 2FA enforcement. Pretix stores no local passwords.
* **Frictionless Attendee Experience:** 1-click checkout for authenticated users. No billing questions, no manual data entry for name/email, free tickets, and automated QR/Apple Wallet delivery.
* **Regional Isolation & Security:** Local meetup organizers must only have access to their specific city's events and attendee data in Pretix, with restricted "View Only" permissions for global financial/event settings.
* **Community Synergy:** Every event ticket and confirmation email must drive traffic back to the Discourse forum for discussion, speaker Q&A, and social sharing.
* **Meetup.com Migration:** Safely transition historical meetup organizers off the Meetup Pro network onto community-owned infrastructure.

---

## 2. Key Design & Implementation Decisions

### Identity & Authentication (SSO)
* **Protocol:** DiscourseConnect (HMAC-SHA256 signature, Base64 payload, single-use nonce).
* **Identity Key:** Discourse's immutable `external_id` (numeric user ID).
* **Security & Blocking:** The Pretix SSO plugin enriches the login payload by querying the Discourse Admin API. Logins are actively blocked if the user is Silenced, Suspended, Anonymized (RTBF), or if they are a Privileged User (Admin/Host) without 2FA enabled.
* **Profile Lock-down:** The `NativeAuthBackend` is completely disabled in Pretix. Users cannot change their email or bypass Discourse authentication locally.

### Checkout Experience
* **Name Pre-population:** The user's real name is pre-filled from their Discourse profile during SSO login. The attendee can edit their name during checkout, but updates are stored only in Pretix — the Discourse profile is never modified.
* **Single Name Field:** Pretix is configured with `name_scheme: "full"` (one field) instead of separate given/family name fields.
* **Minimal Checkout:** Invoice addresses, duplicate email confirmation (`order_email_asked_twice`), payment steps (`payment_term_last: null`), and the copy-answers button are all disabled. The checkout flow is: authenticate via SSO, confirm/edit name, submit.
* **No RSVP Buttons on Forum:** The Discourse `[event]` tag uses `minimal="true"` without `status="public"`, so no Interested/Attending buttons appear. RSVP is handled exclusively through Pretix.

### Event Architecture (The Master Template)
* To guarantee consistent settings across hundreds of global meetups, local organizers **cannot** create events from scratch. 
* A hidden `ansible-meetup-template-v6` is maintained in Pretix. It contains the locked-down checkout settings, zero-cost ticket items, custom HTML social sharing widgets, and email texts.
* All new regional meetups are cloned from this template via API.

### Forum Post Structure (Content Separation)
* Each event's Discourse topic contains a Discourse-specific `[event]` BBCode block at the top, followed by a `---` horizontal rule separator, followed by the human-readable event description.
* When syncing content to Pretix's frontpage, only the content **below** the `---` separator is used. The `[event]` BBCode block is excluded because it does not render outside Discourse.

### Group Permissions (Subcategories vs. Tags)
* **Decision:** Regional Discourse Subcategories (`Events > London`) with **Category Moderators** instead of a flat structure with Tags.
* **Reasoning:** Discourse cannot assign edit/modify permissions based on Tags. By using regional subcategories, we can assign the local host group (`meetup-host-london`) as Category Moderators. This grants them the ability to edit community posts, pin topics, and manage the agenda for their city without requiring global admin rights.

### Workflow: Hub-and-Spoke (Manual MVP)
* **Decision:** Event creation is initiated via a request template on the forum and executed by the Ansible Community Team using a CLI script.
* **Reasoning:** Giving local organizers global "Create Event" permissions in Pretix introduces the risk of template tampering and orphaned events. The CLI approach guarantees events are correctly cloned, quota-adjusted, linked to the forum, and safely sandboxed into the correct regional Team in seconds.

### Privacy: Hidden Attendee Subscriptions
* **Decision:** Map Discourse custom profile dropdowns to *hidden* groups (`meetup-attendee-{city}`) with Visibility Level 3 (Staff Only).
* **Reasoning:** Users can subscribe to city notifications without exposing a public list of residents (preventing location-based doxxing).

---

## 3. Script Inventory & Functions

The integration relies on a unified suite of Python scripts that interact with the Pretix REST API and Discourse REST API. All scripts import shared configuration and API wrappers from a centralized library.

### `ansible_events_lib.py` (Shared Core Library)
* **Role:** Centralized dependency management and configuration.
* **Function:**
  * API environment variable validation (`pre_flight_checks`) with support for Pretix-only mode.
  * Standard Python logging configuration.
  * Type-annotated HTTP request wrappers (`pretix_req`, `discourse_req`) with unified error handling, timeout enforcement, `RequestException` and `JSONDecodeError` handling.
  * `check_event_exists` helper for idempotent template detection.
  * Cities registry (`CITIES`) with structured entries containing region, country, city name, and timezone for each active meetup location (currently: London, Barcelona, FakeTown).
  * City helper functions: `get_city` (case-insensitive lookup). Slug and field value are properties on `CityInfo`.
  * Shared constants: `TEMPLATE_SLUG`, `CONTACT_EMAIL`, `DISCOURSE_PARENT_CATEGORY_ID`, `DISCOURSE_EVENTS_CATEGORY_ID`, `ORGANIZER_SLUG`.
  * `ApiResponse` type alias for the mixed `dict | bool | None` return type used by API wrappers.
  * `pretix_list_all` pagination helper for safely fetching all results from paginated Pretix list endpoints.

### `create_event.py` (CLI Event Provisioning)
* **Role:** Used by the Community Team to safely launch a new regional meetup.
* **Function:**
  1. Creates the Discourse forum topic **first**, authored on behalf of the local organizer (`--host`), with a Discourse Calendar `[event]` widget and a placeholder RSVP link.
  2. Clones the Pretix master template to create the ticketing event, injecting the forum URL as metadata.
  3. Updates the Discourse post with the verified Pretix RSVP URL.
  4. Syncs only the content below the `---` separator to Pretix's frontpage (excluding Discourse-specific BBCode).
  5. Adjusts venue capacity via quota management.
  6. Publishes the event and assigns it to the local city's Organisers Team.
  7. Generates ready-to-paste social media copy for X, Bluesky, Mastodon, LinkedIn, Reddit, and Hacker News, linking back to the forum post.

### `pretix_discourse_auth` (Django Plugin — External)
* **Role:** The inbound/outbound SSO engine running inside Pretix (maintained separately).
* **Function:** 
  * Generates outbound nonces and HMAC signatures.
  * Verifies inbound Discourse payloads.
  * Enforces 2FA and Moderation policies via the Discourse Admin API.
  * Maps Discourse groups (`meetup-host-{city}`) directly to pre-existing Pretix Teams, dynamically granting or revoking dashboard access on every login.
  * Pre-fills attendee name from Discourse SSO payload; local edits in Pretix are never written back to Discourse.

### `pretix-day0.py` (Idempotent Environment Setup)
* **Role:** Zero-touch provisioning for a blank Pretix/Discourse environment. Safe to run repeatedly.
* **Function:** 
  * Creates the global `meetup-admin` Discourse group for the Ansible Community Team (visibility_level 1).
  * Creates per-city Discourse groups (`meetup-host-*`, `meetup-attendee-*`) and regional subcategories from the shared `CITIES` registry, assigning Category Moderator permissions.
  * Configures Pretix global settings and custom meta properties (`forum_topic_url`).
  * Generates the `ansible-meetup-template-v6` with strict SSO-friendly checkout rules (single name field, no duplicate email, no payment step), zero-cost ticket items, ICS attachments, and Passbook plugins.
  * Pre-creates restricted regional Pretix Teams (`Ansible Meetup Organisers - {City}`) with granular permissions (`event.orders:read`, `event.orders:checkin`) so the SSO plugin can map users on day one.

### `pretix-sync-event.py` (One-Way Data Sync)
* **Role:** Keeps Pretix in sync with the Discourse forum (the Source of Truth).
* **Function:** Extracts the `forum_topic_url` from a Pretix event, queries the Discourse API for the first post's raw markdown (via `GET /posts/{id}.json`), strips everything above the `---` separator to exclude the Discourse `[event]` BBCode block, and overwrites the Pretix event's frontpage description with the clean markdown. Guards against empty topic data and missing posts.

### `discourse-connect-mvp.py` (SSO Test Toolkit)
* **Role:** Standalone Flask application for testing and debugging the DiscourseConnect SSO flow.
* **Function:** Implements the full SSO protocol (nonce generation, HMAC verification, payload decode). Enriches login data via the Discourse Admin API to check 2FA status, moderation flags, group memberships, and badges. Renders a diagnostic dashboard showing the computed permission level (admin/host/regular/blocked) and all raw payload data.

### `lint.sh` (Code Quality)
* **Role:** Automated linting and formatting for all Python files.
* **Function:** Runs isort (import ordering), ruff format, ruff check with auto-fix, and py_compile syntax verification across all project scripts.

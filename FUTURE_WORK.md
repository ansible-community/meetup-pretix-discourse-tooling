# Future Enhancements

Organised by attendee lifecycle stage. Each item has a consistent structure: description, status, ROI justification, effort, type, and technical implementation.

---

# Discovery & SEO

## Events Category Landing Page

**Description:** Add an "About the Events Category" pinned topic to `forum.ansible.com/c/events/8` with SEO-friendly text explaining what Ansible Meetups are, how to find your city, how to organise, and how to subscribe to notifications. This is the primary organic landing page — it already ranks page 1 for "Ansible Meetup Barcelona".

**Status:** Unimplemented

**ROI:** HIGH — the category page is the #1 entry point for organic search. A pinned topic with keywords turns a bare topic list into a rich landing page.

**Effort:** Hours

**Type:** Content

### Technical Implementation
* Create a topic in the Events category titled "About the Events Category".
* Pin it globally. Content: what this is, how to find your city, how to organise, subscribe link, CoC, Privacy.
* Per-city subcategory descriptions are already set by `provision_environment.py` with SEO keywords.

---

## Schema.org/Event Structured Data

**Description:** Embed `schema.org/Event` JSON-LD in forum event topics to enable Google Rich Results — event cards with date, location, and RSVP link in search results. Google requires `name`, `startDate`, and a **physical address** for the event carousel.

**Status:** Implemented

**ROI:** MEDIUM — enables Google Event carousel for in-person events with a physical address. JavaScript-injected JSON-LD works (Google renders JS) but with potential delay. The embedded JSON-LD in the post body (via `create_event.py --venue --address`) is server-rendered and immediately visible.

**Effort:** Done

**Type:** Code

### Technical Implementation
* `create_event.py` embeds a `<script type="application/ld+json">` block directly in the forum post with Event schema including `location` (when `--venue`/`--address` provided).
* A Discourse theme component (`discourse-theme/event-jsonld/`) provides fallback JSON-LD by parsing the `.discourse-post-event` widget's `data-*` attributes.
* `meta_noindex: true` is set on Pretix events so the forum page is the only indexed version.
* Verified: forum.ansible.com serves identical HTML to all user agents (no separate crawler view).

### Questions
* Upstream PR to the Discourse Events plugin for server-side JSON-LD (using `:topic_crawler_container_schema` modifier) would be more reliable long-term. The modifier hook exists in core; the plugin doesn't use it.

---

## Luma.com Cross-Listing

**Description:** Create a `luma.com/ansible-community` calendar with "redirect" events pointing to the forum for RSVP. Luma's calendar re-sharing lets related communities (DevOps London, Python Barcelona) cross-promote events to their subscribers — organic discovery driven by community networks, not algorithms.

**Status:** Unimplemented

**ROI:** MEDIUM — high discovery potential via Luma's network effects, but adds a maintenance burden (another platform to keep updated) and risk of attendee confusion.

**Effort:** Hours (manual) / Days (automated)

**Type:** Process + Third-party

### Technical Implementation
* Create `luma.com/ansible-community` calendar (one-time).
* Per event: create a Luma event with "External Registration" pointing to the forum topic URL.
* Optional: expose a global `.ics` feed from Pretix and auto-import into Luma.
* Always link back to forum. Never take RSVPs on Luma.

---

## LinkedIn Events Cross-Posting

**Description:** Create native LinkedIn Events on the Ansible Community company page. LinkedIn prioritises native events in its feed algorithm far more than standard URL posts — reaching tech audiences where they already are.

**Status:** Unimplemented

**ROI:** MEDIUM — high visibility within professional networks, but LinkedIn API for company page events requires OAuth2 admin tokens and ongoing maintenance.

**Effort:** Days

**Type:** Code / Third-party

### Technical Implementation
* Add optional `--linkedin` flag to `create_event.py` or create manually via LinkedIn UI.
* LinkedIn Marketing API requires OAuth2 with a company page admin token.
* Event data: title, date, description, external RSVP URL pointing to forum topic.

---

## Meetup Pro Link Removal

**Description:** Find and update all places across Ansible properties that link to `meetup.com/pro/ansible`. Redirect traffic to the forum Events category. Meetup.com currently ranks #1-2 for city-specific searches.

**Status:** Unimplemented

**ROI:** HIGH — directly redirects existing traffic from high-ranking pages. The single fastest way to build forum page authority.

**Effort:** Hours

**Type:** Process

### Technical Implementation
* **ansible.com/community/events/ansible-meetups** — update to link to forum (high domain authority).
* **Meetup.com group pages** — pin "We've moved" notice with forum link (currently rank #1-2).
* **GitHub repos** (ansible-community/meetup, ansible-community/ansible-london-meetup, etc.) — archive with redirect in README.
* **docs.ansible.com/projects/meetup/** — update to reference forum-based workflow.
* Submit sitemap to Google Search Console; request re-crawl of forum Events category.

---

## UTM Tracking in Social Media Copy

**Description:** Add UTM parameters to forum URLs in social media copy to track which platforms drive RSVPs.

**Status:** Unimplemented

**ROI:** LOW — enables measurement but doesn't directly drive attendance. Useful for optimising promotion effort over time.

**Effort:** Hours

**Type:** Code

### Technical Implementation
* Update `print_social_media_copy()` to append `?utm_source={platform}&utm_medium=social&utm_campaign={city}-{month}-{year}`.
* Discourse's built-in traffic analytics shows referral sources with UTM breakdown.

---

# Signup & RSVP

## Enable Social Login on Discourse

**Description:** The forum account requirement is the biggest RSVP conversion barrier for first-time attendees. Enabling "Log in with GitHub" and "Log in with Google" reduces account creation to one click for most tech users.

**Status:** Unimplemented

**ROI:** HIGH — directly removes the #1 conversion barrier. Most Ansible users already have GitHub accounts. Meetup.com allows one-click Google signup; we should match this.

**Effort:** Hours

**Type:** Config (Discourse admin — no code change)

### Technical Implementation
* Discourse admin: Settings → Login → enable `github_login` and `google_oauth2_enabled`.
* Consider adding prominent text on the RSVP flow: "Free account — 1-click sign up with GitHub or Google."

---

## RSVP Count on Forum Post (Social Proof)

**Description:** Show "32/50 spots filled" on the forum event topic. Social proof drives RSVPs — seeing that others are going reduces hesitation and creates urgency.

**Status:** Unimplemented

**ROI:** HIGH — social proof is one of the strongest psychological drivers of event attendance. Meetup.com prominently shows "X going" on every event.

**Effort:** Days

**Type:** Code

### Technical Implementation
* Script: `sync_rsvp_count.py` (cron, runs hourly).
* Pretix API: `GET .../events/{slug}/orders/?status=p` — count results.
* Discourse API: `PUT /posts/{id}.json` — update a `<!-- rsvp-count -->` placeholder with the count.

---

## "Share I'm Attending" Pretix Plugin

**Description:** Show social share buttons on the Pretix order confirmation page after RSVP, with pre-filled text linking back to the forum topic.

**Status:** Research complete — feasible via `pretix.presale.signals.order_info_top`

**ROI:** MEDIUM — creates an organic promotion loop (each attendee becomes a promoter) but requires a custom Pretix plugin.

**Effort:** Days

**Type:** Code (Pretix plugin)

### Technical Implementation
* Signal: `order_info_top` fires on order detail page, renders above order items.
* Data: `sender.meta_data.get('forum_topic_url')` for the share link.
* Share URLs: X, LinkedIn, Bluesky (web intents), Mastodon (copy-to-clipboard).
* Show for `status == 'p'` (free events are marked "paid" immediately).

---

## Waitlist Management

**Description:** When events reach capacity, enable a waitlist. When someone cancels, Pretix automatically emails the next person with a 24-hour voucher to claim the spot.

**Status:** Unimplemented

**ROI:** MEDIUM — improves attendee satisfaction and venue utilisation, but only matters for events that consistently sell out.

**Effort:** Hours (mostly config)

**Type:** Config + Code

### Technical Implementation
* Enable Pretix Waiting List plugin on the template.
* Optional automation: `pretix-process-waitlist.py` (cron, every 15 min) to auto-send vouchers.
* Pretix handles the email notification natively.

---

## Attendee "Plus One" Guest System

**Description:** Allow registered users to bring one guest without requiring the guest to create a forum account. Reduces friction for casual attendees.

**Status:** Unimplemented

**ROI:** LOW — nice for attendees but adds checkout complexity and makes capacity tracking less precise.

**Effort:** Hours

**Type:** Config (Pretix template question)

### Technical Implementation
* Add checkout question: "Will you bring a guest? (Max 1)".
* Each plus-one consumes two quota slots.
* Guest does not receive a separate badge or email.

---

# Pre-Event (Reducing No-Shows)

## Automated Email Reminders

**Description:** Multi-stage reminder emails to combat the industry-standard 50% drop-off rate for free events. Day-before reminders alone improve attendance by 15-25%.

**Status:** Unimplemented

**ROI:** HIGH — the single highest-impact attendance improvement available. Industry-proven across thousands of free community events.

**Effort:** Weeks

**Type:** Code

### Technical Implementation

| Timing | Subject | Content |
|---|---|---|
| T-7 days | "Next week: {event}" | Agenda, speaker highlights, forum link |
| T-3 days | "{event} this week" | Venue confirmed, updated agenda, cancel link |
| T-1 day | "See you tomorrow" | Venue map/directions, what to bring, QR code, cancel link |
| T-0 morning | "Today: {event} at {time}" | Final directions, start time, QR code |
| T+1 day | "Thanks for coming!" | Recap link, feedback survey, next event teaser |

* Cron job runs hourly, checks event dates against reminder windows.
* Pretix API for attendee list; send via Pretix sendmail plugin or external SMTP.
* Idempotency via local SQLite/Redis to prevent duplicate sends.
* Include cancel link in every reminder (frees spots for waitlist).

---

## City Calendar Feeds (.ics)

**Description:** City-specific webcal:// feeds that auto-populate Google/Outlook/Apple calendars with all future events. Subscribe once, events appear automatically — "set it and forget it" for returning attendees.

**Status:** Unimplemented

**ROI:** HIGH — removes the need for returning attendees to actively check for new events. This is the most requested feature from users migrating off Meetup.com.

**Effort:** Days

**Type:** Code

### Technical Implementation
* Endpoint: `https://events.ansible.com/feeds/{city}.ics` (or hosted via GitHub Pages).
* Query Pretix API for upcoming events filtered by city; generate iCalendar VEVENT entries.
* Regenerate nightly so new events auto-appear.
* Add "Subscribe to Calendar" link in the city subcategory description and forum post template.

---

## Auto-Watch City Subcategory for Attendee Groups

**Description:** Configure `meetup-attendee-{city}` groups to auto-watch their city's Events subcategory so members get Discourse email notifications for new events. Currently, group membership gives no notifications unless the user manually watches the category.

**Status:** Unimplemented

**ROI:** HIGH — ensures subscribed attendees actually learn about new events. Without this, the notification groups are essentially non-functional.

**Effort:** Hours

**Type:** Config (Discourse admin — no code change)

### Technical Implementation
* Discourse admin: For each `meetup-attendee-{city}` group → Settings → "Default notification level for categories" → set city subcategory to "Watching".
* Can be automated via `provision_environment.py` using `PUT /admin/groups/{id}.json` with `watching_category_ids`.

---

## Social Media Reshare Injection

**Description:** After the community team publishes official social media posts, append their URLs to the forum topic so attendees can reshare them.

**Status:** Unimplemented

**ROI:** LOW — convenience feature; attendees can already share the forum link directly.

**Effort:** Hours

**Type:** Code

### Technical Implementation
* Script: accepts topic ID + social media URLs, appends a "Help us spread the word!" block to the post.

---

# At the Event

## First-Timer Welcoming Protocol

**Description:** Add a Pretix checkout question: "Is this your first Ansible Meetup?" The check-in app shows the answer. Give organisers coloured stickers for first-timer name badges so existing members proactively welcome them.

**Status:** Unimplemented

**ROI:** HIGH — first-timer welcome is the single highest-impact action for return attendance at community events. Costs almost nothing to implement.

**Effort:** Hours

**Type:** Config (Pretix template question) + Process

### Technical Implementation
* Add boolean checkout question to the master template.
* PretixSCAN displays custom question answers when scanning.
* Provide organisers with dot stickers or distinct badge inserts.

---

## Check-in & Device Provisioning

**Description:** Automate the generation of PretixSCAN device initialization codes so organisers can set up the check-in app without manual admin intervention.

**Status:** Partially implemented (PretixSCAN works natively; device code generation is manual)

**ROI:** MEDIUM — reduces admin overhead but only affects the initial setup per-organiser.

**Effort:** Hours

**Type:** Code

### Technical Implementation
* Pretix API: `POST /api/v1/organizers/{org}/devices/` returns `initialization_token`.
* Add optional `--setup-checkin` flag or separate script.
* Send the code to the organiser via Discourse private message.
* Device inherits the team's event permissions (city-scoped).

---

## Name Badges

**Description:** Generate printable name badges from Pretix attendee data. The `pretix.plugins.badges` plugin is already enabled on the template.

**Status:** Partially implemented (plugin enabled, badge template not configured)

**ROI:** LOW — improves on-site professional feel and networking, but many community meetups skip badges.

**Effort:** Hours

**Type:** Config

### Technical Implementation
* Configure badge template in Pretix admin (standard Avery label format).
* Organisers print badges at the check-in desk or before the event.

---

# Post-Event & Retention

## Attendance Badges & Gamification

**Description:** Automatically award Discourse badges to users who check in at events. Tiered badges: "First Meetup", "5 Meetups", "Meetup Champion (25+)".

**Status:** Unimplemented

**ROI:** MEDIUM — creates visible community status and encourages return attendance, but requires a middleware script to bridge Pretix check-ins to Discourse badges.

**Effort:** Days

**Type:** Code

### Technical Implementation
* Nightly cron job: query Pretix for events ended in the last 24 hours, fetch check-in positions, extract Discourse `external_id`.
* Discourse API: `POST /user_badges.json` to award badges.
* Idempotent: Discourse ignores duplicate awards if badge is "can be granted multiple times: False".

---

## Automated Post-Event Recap Prompt

**Description:** Send organisers a DM 24 hours after their event: "How did it go? Reply to the event topic with a recap and photos." Include a template with sections for highlights, thanks, and next event teaser.

**Status:** Unimplemented

**ROI:** MEDIUM — drives recap content which builds social proof for future events, but depends entirely on organiser follow-through.

**Effort:** Hours

**Type:** Code

### Technical Implementation
* Cron job identifies events ended 24h ago.
* Send Discourse DM to the organiser with a recap template and link to the event topic.
* Include "Save the date" prompt for the next event.

---

## Event Feedback Collection

**Description:** Send post-event surveys to checked-in attendees. Aggregate results for organisers.

**Status:** Unimplemented

**ROI:** MEDIUM — provides critical feedback for improving future events, but survey fatigue is real.

**Effort:** Days

**Type:** Code

### Technical Implementation
* Survey via Discourse Polls (embedded in event topic reply) or Google Forms.
* Questions: overall rating, venue, content, "would you attend again?", free-text.
* Results posted as private reply to organisers + anonymised public summary.

---

## No-Show Tracking

**Description:** Track users who repeatedly RSVP but don't attend. Optionally throttle serial no-shows to waitlist for high-demand events.

**Status:** Unimplemented

**ROI:** LOW — only relevant for consistently oversubscribed events. Controversial — could alienate community members.

**Effort:** Days

**Type:** Code

### Technical Implementation
* Nightly job compares Pretix orders vs check-ins.
* Store no-show count in Discourse user custom field.
* Optional: after 3+ consecutive no-shows, auto-waitlist on next RSVP.

### Questions
* Requires community policy decision before implementation. Risk of discouraging RSVPs if people fear being tracked.

---

## Video Recording & Archiving

**Description:** Encourage organisers to record talks and upload to the Ansible Community YouTube channel. Embed in the Discourse event topic as a reply.

**Status:** Unimplemented

**ROI:** LOW (short-term) / HIGH (long-term SEO) — YouTube videos rank independently for specific technical queries, but recording quality varies and adds organiser burden.

**Effort:** Hours (process) / Weeks (if editing)

**Type:** Process

### Technical Implementation
* Recommend smartphone on tripod + lavalier mic for decent audio.
* Upload to Ansible Community YouTube channel (or dedicated meetups playlist).
* Reply to forum topic with embed link.

---

# Organiser Experience

## New Organiser Onboarding DM

**Description:** Auto-send a welcome private message when someone is added to a `meetup-organisers-{city}` group with links to the organiser guide, 2FA instructions, and check-in app setup.

**Status:** Unimplemented

**ROI:** MEDIUM — reduces organiser confusion and support requests, but only affects the initial onboarding experience.

**Effort:** Hours

**Type:** Config (Discourse Automation Plugin)

### Technical Implementation
* Discourse Automation rule: trigger on "User added to group" matching `meetup-organisers-*`.
* DM template with links to organiser guide, 2FA path, pretixSCAN download.

---

## Recurring Event Series

**Description:** Create monthly or quarterly event series with a single command. Reduces organiser workload for regular meetups.

**Status:** Unimplemented

**ROI:** MEDIUM — saves time for active organisers but the current one-at-a-time CLI is workable.

**Effort:** Days

**Type:** Code

### Technical Implementation
* Script: `pretix-create-series.py` with `--recurrence` (monthly/quarterly), `--start-date`, `--duration-months`.
* Calculate dates via `dateutil.rrule`, loop through `create_event.py` logic.
* Tag related Discourse topics with a series tag.

---

## Organiser Analytics Dashboard

**Description:** Self-service reporting for organisers: attendance trends, no-show rates, growth metrics, repeat attendee percentage.

**Status:** Unimplemented

**ROI:** MEDIUM — empowers data-driven decisions and sponsor pitches, but adds a web application to maintain.

**Effort:** Weeks

**Type:** Code

### Technical Implementation
* Web app authenticated via Discourse SSO, scoped by `meetup-organisers-{city}` group.
* Nightly data pipeline: Pretix orders + check-ins → PostgreSQL time-series.
* Dashboard: month-over-month growth, no-show rate, retention, peak registration times.

---

## Automated Event Creation via Webhooks

**Description:** Replace CLI-based event creation with a forum-driven workflow: organiser moves a topic from "Meetup Requests" to "Events", triggering automatic Pretix event provisioning.

**Status:** Unimplemented (deferred for post-MVP maturity)

**ROI:** MEDIUM — removes the Community Team bottleneck but introduces risks of template tampering and orphaned events.

**Effort:** Weeks

**Type:** Code

### Technical Implementation
* Discourse Automation Plugin: webhook on topic category change.
* Middleware (Lambda/GitHub Actions): parse topic, execute create_event logic, post confirmation reply.

---

## Sponsor Acknowledgement in Event Template

**Description:** Add a "Supported by" section to the forum post template for venue hosts and sponsors.

**Status:** Unimplemented

**ROI:** LOW — encourages continued sponsor support but doesn't directly drive attendance.

**Effort:** Hours

**Type:** Code (template change)

### Technical Implementation
* Add `### Supported by` section with placeholder text.
* Document sponsor guidelines in the organiser guide.

---

## Dynamic Speaker Social Cards

**Description:** Generate branded social sharing images when speakers are confirmed. Speakers share personalised cards on LinkedIn/X: "I'm speaking at Ansible Meetup London."

**Status:** Unimplemented

**ROI:** LOW — creates an organic promotion loop from speakers' networks, but requires image generation infrastructure.

**Effort:** Days

**Type:** Code

### Technical Implementation
* Serverless image generation (Vercel OG / headless browser).
* Template: speaker name, talk title, event name, city, date, Ansible logo.

---

# Infrastructure & Security

## Apple/Google Wallet Passes

**Description:** Generate wallet passes so attendees can add tickets to Apple Wallet or Google Wallet from the confirmation email.

**Status:** Partially implemented (`pretix-passbook` in TEMPLATE_PLUGINS, passbook back field set to forum URL)

**ROI:** MEDIUM — polished attendee experience, but most attendees just show the QR code from their email.

**Effort:** Hours (config on Pretix server)

**Type:** Config

### Technical Implementation
* `pip install pretix-passbook` on Pretix server.
* Upload Apple Developer certificate for .pkpass signing.
* Google Wallet requires separate Google Pay API merchant setup.
* Already enabled in template plugins; back field already links to forum URL.

---

## Nightly Security Reconciliation

**Description:** Nightly scan to detect Discourse users who've been suspended, deleted, or anonymised since their last Pretix login. Generates an alert for the Community Team.

**Status:** Unimplemented

**ROI:** MEDIUM — defence-in-depth for data protection. Currently enforced on next login, but a nightly scan catches inactive users.

**Effort:** Days

**Type:** Code

### Technical Implementation
* Cron job: fetch all Pretix users, check each against Discourse Admin API.
* Flag: 404 (deleted), `suspended_till` (suspended), `@anonymized.invalid` email (RTBF).
* Email report to `ansible-community-events@redhat.com`.

---

## Avatar Syncing

**Description:** Show Discourse avatars in the Pretix control panel.

**Status:** Deferred

**ROI:** LOW — cosmetic improvement. CDN-signed Discourse avatar URLs expire after 7 days.

**Effort:** Days

**Type:** Code (Pretix plugin)

### Technical Implementation
* Plugin listens to `pretix.control.signals.html_head`, fetches avatar URL on login, caches in Redis for 24h.

---

## Single Sign-Out

**Description:** Logging out of Pretix also logs out of Discourse, and vice versa.

**Status:** Deferred

**ROI:** LOW — high engineering effort for a feature most users never think about.

**Effort:** Weeks

**Type:** Code

### Technical Implementation
* Pretix → Discourse: redirect to `/session/sso_provider/logout`.
* Discourse → Pretix: webhook to `/_discourse/slo` endpoint to invalidate Django session.

---

## Cross-City Event Promotion

**Description:** Surface nearby or related events to users based on their city subscriptions.

**Status:** Unimplemented

**ROI:** LOW — nice for discovery but requires a proximity model and custom Discourse plugin.

**Effort:** Weeks

**Type:** Code

### Technical Implementation
* Discourse plugin: query user's `meetup-attendee-{city}` groups, show nearby events in sidebar.
* Weekly email digest highlighting events in subscribed + nearby cities.

---

## Meetup.com Import Tool

**Description:** Import historical event data from Meetup Pro into Discourse as read-only archive topics.

**Status:** Partially implemented (meetup_list_groups.py and meetup_list_organisers.py exist for data extraction)

**ROI:** LOW — preserves history but attendees rarely look at past events. Organiser contact export is the high-value piece (already built).

**Effort:** Days

**Type:** Code

### Technical Implementation
* Create read-only Discourse topics in an "Event Archive" category.
* Tag with `#meetup-legacy` and city name.
* Do NOT create Pretix events for historical data.

---

# Security Hardening

## Resolved

| Severity | Fix |
|---|---|
| HIGH | XSS in `/debug` endpoint — HTML-escaped |
| HIGH | XSS in 403 error page — HTML-escaped |
| HIGH | SSO nonce bypass — empty nonces rejected |
| MEDIUM | PII in logs — response bodies truncated to 200 chars |
| MEDIUM | CLI input validation — `--city` regex, `--slug` alphanumeric |
| MEDIUM | URL parsing — `urlparse` + numeric validation |
| MEDIUM | Organiser validation — group membership checked before impersonation |

## Open (Accepted Risk)

**Markdown relay (Discourse → Pretix)**

* **Risk:** `pretix-sync-event.py` copies raw markdown to Pretix. A malicious organiser could inject markdown that renders dangerously in Pretix's renderer.
* **Mitigation:** Only trusted organisers (verified group members) can edit event content.
* **Future:** Validate markdown against a safe-element allowlist before writing to Pretix.

**SSO test toolkit**

* **Risk:** `discourse-connect-mvp.py` has a default Flask secret key and unauthenticated `/debug` endpoint.
* **Mitigation:** Explicitly a localhost-only dev tool, never deployed.
* **Future:** If deployed beyond localhost: require `FLASK_SECRET`, gate `/debug`, enforce `SESSION_COOKIE_SECURE=True`.

# Proposal: Bringing Ansible Meetups Home to the Forum

Hey everyone,

The Ansible Community Team has been working on something we'd like your input on. We're proposing a new approach to how we run Ansible community meetups worldwide — one that brings events closer to where the community already lives: right here on the forum.

This post explains what we're thinking, why, and how it would work. **We want your feedback before we finalise anything**, so please read through and share your thoughts — especially the questions at the end.

---

## What we're proposing

We want to move Ansible community meetups off Meetup Pro (`meetup.com/pro/ansible`) and onto **community-owned infrastructure** built around two open-source tools:

- **This forum** (Discourse) — for identity, event content, discussion, and community
- **Pretix** (self-hosted) — for RSVP, capacity management, QR check-in, and ticket delivery

The forum becomes the event page. Pretix handles the behind-the-scenes logistics. Your forum account ties it all together.

---

## Why we're considering this

We've been running Ansible meetups on Meetup Pro for years, and it's worked. But a few things have been nudging us toward a change:

**Ownership.** Meetup.com owns the data — attendee lists, event history, organiser contacts. If the platform changes its terms, pricing, or feature set, we have no recourse. Community infrastructure should be owned by the community.

**Cost.** Meetup Pro isn't free. The budget spent on platform fees could go toward other community initiatives — speaker travel, swag, tooling.

**Per-city flexibility.** Meetup Pro pricing forced us to consolidate groups to control costs. For example, the 11 Indian Ansible meetup groups had to merge into a single "Ansible India" group — losing the local identity of cities like Pune, Bangalore, Hyderabad, and Chennai. With community-owned infrastructure, there's no per-group cost. Every city gets its own group, its own subcategory, its own organiser team. We can restore the local meetup identity that consolidation took away.

**Fragmentation.** The Ansible community discusses things here on the forum. Events live on Meetup. Attendees have to context-switch between two platforms, two accounts, two notification systems. We'd rather have everything in one place.

**Integration.** With community-owned tools, we can build exactly what we need: SSO that works with your forum account, scoped permissions for organisers, automated social sharing, and privacy-respecting attendee management.

---

## Objectives

1. **Single identity** — Your forum account is your event account. One login, everywhere.
2. **Frictionless RSVP** — Sign in, confirm your name, done. No billing screens, no payment steps, no duplicate email prompts. You get a QR code and calendar attachment by email.
3. **Organiser autonomy** — Local organisers manage their own city's events by editing a forum topic. They can see their attendee list and check people in at the door. They cannot see other cities' data.
4. **Data ownership** — All event data lives on infrastructure the community controls. No vendor lock-in.
5. **Privacy by design** — City subscriptions are hidden. Attendee lists are restricted to organisers. Location-based doxxing is architecturally prevented.
6. **Consistency** — Every meetup worldwide has the same checkout experience, the same QR delivery, the same check-in process. No per-city configuration drift.

---

## How it works

### For attendees

1. You see an event topic in the Events category on the forum.
2. You click the RSVP link, which takes you to Pretix.
3. Pretix recognises you via your forum login (SSO) — no new account needed.
4. Your name is pre-filled from your forum profile. You can edit it if you want (the edit stays in Pretix only — your forum profile is never changed).
5. You submit. That's the entire checkout.
6. You get a confirmation email with a QR code and an `.ics` calendar attachment.
7. At the door, the organiser scans your QR code. Done.

**Want to discuss the event?** Reply to the forum topic. Ask questions, propose a talk, coordinate with other attendees — it's all in one place.

### For organisers

1. You ask the Ansible Community Team to set up a meetup for your city (via a forum request).
2. We create the event: a forum topic authored on your behalf, linked to a Pretix ticketing page.
3. You edit the forum topic to update the agenda, add speakers, change the venue. Your changes sync to the ticketing page automatically.
4. You get access to a scoped Pretix dashboard where you can see who's registered and check people in at the door using the Pretixdroid/Pretixscan mobile app.
5. You **cannot** see other cities' data, change global settings, or modify the checkout flow. Your scope is your city's events only.

### For the Ansible Community Team (admins)

1. We maintain a master event template in Pretix with locked-down settings (free tickets, single name field, no billing, QR delivery).
2. When an organiser requests a new event, we run a CLI command that: creates the forum topic, clones the template, links them together, sets the capacity, assigns the organiser's team, and generates social media copy for 6 platforms.
3. We manage the cities registry, the Discourse groups, and the Pretix teams. Adding a new city takes seconds.
4. Pretix administrators manage the Pretix-only `Ansible Meetup Staff` team, which has access to all meetup events. The Forum has no staff or admin group that grants Pretix access.

---

## Data protection & security

We've thought carefully about this:

**Authentication.** Pretix doesn't store passwords. All authentication flows through Discourse SSO (DiscourseConnect, HMAC-SHA256 signed). If your forum account is suspended, silenced, or anonymised (right to be forgotten), you're automatically blocked from RSVP.

**2FA enforcement.** Organisers and staff must complete Discourse's two-factor challenge during login. Pretix accepts privileged access only when DiscourseConnect's signed response confirms the challenge succeeded.

**Regional isolation.** Each city has its own Pretix Team with scoped permissions. London organisers see London attendees. They cannot view, edit, or export data from any other city.

**Privacy.** City notification subscriptions use hidden Discourse groups (staff-only visibility). Nobody can see a public list of who's subscribed to events in a particular city. Attendee lists are visible only to the city's organisers and the Community Team.

**Data minimisation.** The RSVP checkout collects only your name (pre-filled, editable). No billing address, no phone number, no demographic data. Email comes from your existing forum account.

**No vendor lock-in.** Both Discourse and Pretix are open source. The event data, attendee lists, and community content are all on infrastructure we control.

---

## Promoting events — ideas we're exploring

Moving off Meetup.com means we lose its built-in discoverability (search, recommendations, "events near you"). We need to replace that. Here's what we're thinking:

**Immediate (built into the tooling):**
- Social media copy generation — when we create an event, the tooling outputs ready-to-paste text for X, Bluesky, Mastodon, LinkedIn, Reddit, and Hacker News. All posts link back to the forum topic.
- Forum calendar integration — events show up in the Discourse calendar widget with dates and links.

**Short-term:**
- Event discovery page at `events.ansible.com` — a public, SEO-optimised listing of all upcoming meetups with city filtering and schema.org markup for Google Rich Results.
- City-specific calendar feeds (`.ics`) — subscribe once, and all future events in your city auto-populate your Google/Outlook/Apple calendar.
- Automated email reminders — 1 week, 1 day, and 3 hours before the event, matching the cadence people expect.

**Longer-term:**
- Cross-city promotion — if you're subscribed to London events, we surface nearby events (e.g., Manchester, Barcelona) you might also be interested in.
- Post-event photo galleries and recaps to build social proof and attract new attendees.
- Speaker proposal pipeline — a structured way to submit and manage talk proposals through the forum.
- Organiser analytics dashboard — attendance trends, no-show rates, growth metrics, all self-service.

**We'd love your ideas here.** How do you currently find out about tech meetups? What would make you more likely to attend or share an event?

---

## Questions for you

### If you're an attendee (or would-be attendee):

1. Is signing in with your forum account a barrier, or does it make things simpler?
2. Would you miss anything specific from Meetup.com that we haven't mentioned?
3. How do you prefer to be reminded about events? (Email, calendar, forum notification, something else?)
4. Would city-specific calendar feeds (subscribe once, auto-populated) be useful to you?
5. What would make you more likely to share an event with colleagues?

### If you're a meetup organiser:

1. Is editing a forum topic an acceptable way to manage your event page, or do you need a more structured interface?
2. What information do you need to see about your attendees? (Names? Dietary requirements? Company? Or just a headcount?)
3. How important is it to you to keep your Meetup.com group active during the transition?
4. Would you use a mobile check-in app at the door, or do you prefer a printed list?
5. What's the hardest part of organising a meetup today that we could make easier?

### If you're on the Ansible Community Team (admin):

1. Should we automate event creation via forum webhooks (organiser moves topic to "approved" → event auto-provisioned), or keep the CLI approach?
2. How do we handle the transition for cities with active Meetup groups? Parallel operation? Hard cutover with a date?
3. Should we invest in a public event discovery page early, or focus on making the core workflow solid first?

---

## Timeline

We're piloting this now with **London** and **Barcelona**. If you're in either city and want to help test, let us know.

More cities will come online as organisers sign up. If you want to run an Ansible meetup in your city — or you already do and want to move to this platform — reply below or reach out to the Community Team.

During the transition, existing Meetup groups stay active. We won't switch anything off until organisers are comfortable and attendees know where to go.

---

## What we're asking

This is a proposal, not a fait accompli. We've built the tooling, tested the workflow, and we think it's ready — but we want the community's input before we commit to rolling it out broadly.

Tell us:
- Does this approach make sense?
- What are we missing?
- What concerns do you have?
- What would make you excited about this?

Reply below. This is your community infrastructure — help us get it right.

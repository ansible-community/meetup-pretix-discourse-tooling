# Organiser Guide: Running an Ansible Community Meetup

This guide is for local meetup organisers. You don't need to be an engineer — if you can edit a forum post, you can run a meetup.

---

## How It All Fits Together

Before diving in, here's a quick overview of the key concepts, systems, and terms you'll encounter.

### The two systems

| System | What it does | You use it for |
|---|---|---|
| **Discourse** (`forum.ansible.com`) | Identity, event content, community discussion | Editing your event page, managing talk proposals, posting recaps |
| **Pretix** (ticketing) | RSVP, attendee management, QR check-in | Viewing who's registered, checking people in at the door |

You log in to both with your **forum account** — one identity, no separate passwords.

### Forum structure

| Forum element | What it is |
|---|---|
| **Events category** | The parent category for all Ansible meetups |
| **City subcategory** (e.g., `Events > London`) | Your city's dedicated space under Events |
| **Event topic** | A forum post that IS your event page — attendees see it, you edit it |

### Groups and roles

| Group | Who's in it | What it grants |
|---|---|---|
| `meetup-organisers-{city}` (e.g., `meetup-organisers-london`) | You and any co-organisers for your city | Visible only to group owners; its member list is also visible only to group owners. Discourse tracks your city's subcategory by default. Full category access and moderator status only on your city's subcategory + scoped Pretix dashboard access. Forum Admin adds members. |
| `meetup-attendee-{city}` | People who subscribe to your city's events | Staff-only group with a staff-only member list for notification subscriptions |

Everyone on the forum can read and reply to event topics. Only that city's organiser group can start new topics, so new event topics are created by the Community Team in the matching city subcategory.

### What the Community Team handles vs. what you handle

| Community Team does | You do |
|---|---|
| Creates your city (groups, categories, Pretix team) | Edit your event page (venue, agenda, speakers) |
| Creates each event (forum topic + Pretix ticketing) | Promote the event and manage talk proposals |
| Manages capacity and global settings | Check people in at the door |
| Generates social media copy | Post recaps and photos after the event |

### Key requirement: two-factor authentication

As an organiser, you have access to attendee data (names, emails). You **must** use two-factor authentication (2FA) on your forum account. DiscourseConnect challenges you during login, and Pretix accepts the session only when Discourse's signed response confirms that the challenge was completed. The check cannot be disabled in Pretix.

**How to enable 2FA:**
1. Go to `forum.ansible.com` → your profile → **Preferences** → **Security**
2. Click **Enable Two-Factor Authentication**
3. Choose your method (authenticator app recommended) and follow the prompts

If 2FA is not set up or the challenge is not completed, Discourse will not provide the confirmation Pretix requires, and login is denied.

---

## Your Event Page

### The forum topic IS your event page

When the Community Team creates your event, a forum topic is automatically posted in your city's Events subcategory. This topic is **your event page**. It's where attendees find all the information about your meetup.

The topic is posted on your behalf (your username appears as the author), and you have full editing rights as a Category Moderator.

### What the event topic looks like

The topic is created with a structured template:

```
[event block]        ← Calendar widget (don't touch this)
---                  ← Separator (don't delete this)
Details table        ← Date, time, venue, cost, organiser
Agenda table         ← Time slots with speakers
RSVP link            ← Link to Pretix ticketing page
Share section        ← Pre-written text for attendees to share
Connect section      ← Discussion space
```

### Editing the event page

To update your event, edit the forum topic:

1. Click the pencil icon on the first post.
2. Update whatever you need — venue details, agenda, speaker names.
3. Save.

**What you'll most often edit:**

- **Venue** — Replace `*To be announced*` in the Details table with the actual address.
- **Agenda** — Replace the `*Open for proposals*` rows with confirmed speakers and topics.
- **Description** — Add extra information: parking, accessibility, food/drink, sponsor details.

**Important:** Don't delete the `---` horizontal rule near the top of the post. Everything above it is the calendar widget (handled automatically). Everything below it is your event content that syncs to the ticketing page.

### Syncing changes to the ticketing page

Your forum edits are the source of truth. The Community Team can run a sync command that pulls your latest forum content into the Pretix ticketing page. If you make a major update (like adding the venue), let them know so they can sync it.

---

## Managing Your Event

### Checking who's registered

1. Navigate to the Pretix dashboard (the Community Team will give you the URL).
2. Click "Log in with Discourse" and sign in with your forum credentials.
3. You'll see your city's events listed.
4. Click an event to see the attendee list — names, registration status, and email addresses.

You can **only** see events for your own city. You cannot view other cities' data or change global settings.

### Understanding the numbers

| Metric | Meaning |
|---|---|
| **Registered** | People who've completed their RSVP |
| **Capacity** | Venue limit (set by the Community Team) |
| **Available** | Remaining spots |
| **Checked in** | People scanned at the door (on event day) |

### What you can't do (by design)

- Create new events (the Community Team does this for consistency)
- Change the ticket price (always free)
- Modify checkout settings (locked to the standard template)
- View other cities' attendee data

If you need any of these changed, ask the Community Team.

---

## Check-in at the Door

### Setting up the check-in app

The easiest way to check people in is with a phone app that scans QR codes.

1. **Download the app:**
   - Android: search "pretixSCAN" in the Play Store
   - iOS: search "pretixSCAN" in the App Store

2. **Get your initialization code:**
   - The Community Team will generate a device code for you and send it via a private message on the forum.
   - This code links the app to your city's events. It's single-use — enter it once.

3. **Initialize the app:**
   - Open pretixSCAN → tap "Configure" → enter the initialization code.
   - The app downloads your event's attendee list.

4. **You're ready to scan.**

### On the day

- Open the app and select your event.
- Scan the QR code on each attendee's phone (from their confirmation email) or printed ticket.
- Green checkmark = valid. Red X = problem (already checked in, invalid, etc.).
- The check-in count updates in real time.

### Offline mode

The app works without internet. It downloads the attendee list when you connect, and syncs check-in data when back online. Useful for venues with poor wifi.

### Browser-based check-in (alternative)

If you'd rather not install an app, use the web-based check-in in the Pretix dashboard: log in → go to your event → click "Check-in lists" in the sidebar. Requires a stable internet connection.

---

## Promoting Your Event

### Share the forum link, not the Pretix link

The forum topic is where the discussion happens. The Pretix link is just for RSVP. Always share the forum topic URL — attendees can read the agenda, ask questions, and click through to RSVP from there.

### Social media copy

When the Community Team creates your event, they generate ready-to-paste social media text for X, Bluesky, Mastodon, LinkedIn, Reddit, and Hacker News. They'll share this with you — each version is tailored for the platform.

### Where to promote

- Reply to the forum topic to bump it and show activity
- Your local tech Slack or Discord servers
- University CS departments and student societies
- Local Linux user groups, DevOps meetups, Python user groups
- Your company's internal channels
- Local tech event calendars and mailing lists

### Encourage attendees to share

The event topic includes a "Share" section with pre-written text attendees can copy after they RSVP:

> I'm going to Ansible Meetup London on October 31! Free automation meetup with talks, networking, and community. RSVP: [forum link]

---

## Handling Talk Proposals

Attendees propose talks by replying to the forum topic. As a category moderator, you can:

- **Pin** a proposal reply to highlight it
- **Reply** to ask for details or suggest a time slot
- **Edit the agenda table** in the original post when you confirm a speaker

**Tips:**
- Be welcoming — first-time speakers are the backbone of community meetups
- Lightning talks (5-10 minutes) lower the barrier for new speakers
- Mix beginner and advanced topics, demos and discussions

---

## After the Event

### Post a recap

Reply to the forum topic with:
- A thank-you to speakers and attendees
- A brief summary of what was discussed
- Photos from the event (Discourse supports image uploads)
- Follow-up links or resources from speakers

This builds social proof for future events and gives people who missed it a sense of what happened.

### Badge awards

The Community Team is working on automatic badge awards for attendees who check in at the door (e.g., "Meetup Attendee 2026"). This is handled automatically — you don't need to do anything.

---

## FAQ

**How do I create a new event?**
Ask the Community Team. They run a script that creates the forum topic, ticketing page, and permissions. Takes a few minutes.

**Can I change the venue capacity?**
Ask the Community Team to update the quota. They can do this at any time.

**What if someone can't attend?**
They cancel via the link in their confirmation email. The spot frees up automatically.

**Can I see attendee email addresses?**
Yes, in the Pretix dashboard for your city's events only.

**What if the event is full?**
Waitlist support is planned. For now, ask the Community Team to increase capacity if the venue allows it.

**How do I add a co-organiser?**
Ask the Community Team to add them to your city's `meetup-organisers-{city}` group. They'll get the same access as you.

**What if I need to cancel an event?**
Contact the Community Team. They'll unpublish the event and notify registered attendees.

**Do attendees need a forum account?**
Yes. When they click RSVP, they sign in with their forum account. Creating one takes a minute.

**Why do I need 2FA?**
As an organiser you can see attendee names and emails. 2FA protects this data. It's enforced automatically — you can't access the Pretix dashboard without it.

**Who do I contact for help?**
Reply to any topic in the Events category and tag the Community Team, or send a private message on the forum.

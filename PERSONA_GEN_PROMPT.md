# Persona Generation Brief

You are generating sample-user data + profile images for a daily personal-assistant agent POC. Read the project's `POC_Spec.md` first if you have access — otherwise the context below is enough.

---

## Mission

Produce 4 demo personas living at `backend/data/users/<slug>/` with:

1. `meta.json` — minimal identity fields.
2. `profile.md` — extensive markdown preferences profile (treat as the output of a 30–40 min onboarding interview).
3. `mailbox.json` — full historical Gmail inbox spanning the **last 12 months ending 2026-04-30** (yesterday). The agent's `gmail_search` tool will query this.
4. `calendar.json` — full calendar spanning roughly the last 6 months and the next 6 months. The agent's `calendar_search` tool will query this.
5. `fixtures/2026-05-01.json` — the daily cron payload for "today" (2026-05-01). This is what gets pasted into the right-panel input box. Contains a slice of mail (yesterday's window) + calendar (today + upcoming days).

> **Note:** Aditi's `meta.json` and `profile.md` already exist at `backend/data/users/aditi/`. Read them as the gold reference for tone and depth, and only generate her remaining 3 files (`mailbox.json`, `calendar.json`, `fixtures/2026-05-01.json`). For the other 3 personas, generate all 5 files.

---

## The 4 personas

Diversity is the goal — different region, age, life-stage, profession, cultural rooting.

| #   | Slug       | Name           | Age | City                             | Onboarded  | Run state    | Vibe                                                                                                                                                                                  |
| --- | ---------- | -------------- | --- | -------------------------------- | ---------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `aditi`    | Aditi Sharma   | 28F | Bangalore (Indiranagar)          | 2026-02-15 | Steady-state | Fintech PM at "Karman", Delhi-Punjabi origin, dating Karan, foodie/runner/indie-music, urban-cosmopolitan                                                                             |
| 2   | `arjun`    | Arjun Banerjee | 42M | Kolkata (Park Street area)       | 2026-05-01 | First-run    | Owns a contemporary art gallery, Bengali, married to Mitali (interior designer), 2 kids (Ishaan 14, Maya 11), classical music + theatre + cinema                                      |
| 3   | `devendra` | Devendra Patel | 55M | Ahmedabad (Bodakdev)             | 2026-01-20 | Steady-state | Runs a CA practice ("Patel & Associates"), Gujarati, married to Hetal, 2 grown kids (daughter Riya in US, son Krish joining the practice), traditional, religious (Jain), cricket-mad |
| 4   | `meera`    | Meera Pillai   | 24F | Mumbai (Parel residents' hostel) | 2026-05-01 | First-run    | Junior resident doctor at KEM Hospital, Malayali (parents in Kochi), single, K-drama enthusiast, financially stretched on stipend, family pressure to settle down                     |

For each persona you create from scratch (Arjun, Devendra, Meera): write the profile.md to match Aditi's depth — covers identity, schedule, food, music, hobbies, travel, ≥10 important dates, relationships (partner + family + friends with their preferences), bills/subscriptions, shopping/wishlist, commitments style, notes-for-the-assistant. **Adapt every section to the persona** — Devendra's food section won't mention Truffles, it'll mention Agashiye and Vishalla; Meera's shopping section is constrained by her stipend.

---

## File: `meta.json`

```json
{
  "slug": "<slug>",
  "name": "<full name>",
  "email": "<plausible gmail>",
  "city": "<city>",
  "neighbourhood": "<neighbourhood>",
  "timezone": "Asia/Kolkata",
  "onboarded_at": "<YYYY-MM-DD>"
}
```

---

## File: `profile.md`

Markdown. Use the same section structure as Aditi's existing `profile.md`. Required sections:

1. Header with name, "Last updated: 2026-04-30", and onboarded date
2. Identity & Location
3. Schedule (wake, work, recurring meetings, gym/hobby slots)
4. Food (loves, hates, recurring patterns, dietary, Instamart/staples)
5. Music & Hobbies
6. Travel (home airport, frequent destinations, preferred airlines, recent trips, upcoming booked trips, wishlist destinations)
7. Important Dates (table format, ≥10 entries — include partner, parents, siblings, partner's parents, kids if any, close friends, festivals)
8. Relationships (partner with their preferences for gifting cues; family with their preferences; close friends; people to keep in touch with)
9. Bills & Subscriptions (specific Indian providers — BESCOM/MSEB/Torrent Power for electricity by city; specific bank cards; SIPs; insurance)
10. Shopping & Wishlist (brands actually bought, active wishlist, sales tracked)
11. Commitments style (tools, things they drop, nudges that work)
12. Notes for the assistant (tone preferences, sensitivities)

**Realism rules:**

- Use real Indian brand names: Swiggy, Zomato, Blinkit, Instamart, Zepto, Indigo, Vistara/Air India, BESCOM/Torrent Power/Adani Electricity (correct one for the city), HDFC/ICICI/SBI cards, Razorpay, Zerodha, Indmoney, etc.
- Use real Indian neighbourhoods, restaurants, gyms, parks for each city.
- Each persona's profile must contain at least 2–3 city-specific references (a local park, a local restaurant chain, a local landmark).
- Names of people in their lives should be culturally consistent (Punjabi names for Aditi's family, Bengali for Arjun's, Gujarati for Devendra's, Malayali for Meera's).

---

## File: `mailbox.json`

Full historical inbox spanning **2025-05-01 → 2026-04-30** (last email = yesterday). Density target: **60–100 emails per persona**, spread across the 12 months — not bunched at the end.

**Schema:**

```json
{
  "messages": [
    {
      "id": "msg_001",
      "thread_id": "thr_001",
      "from": "<sender name <sender@email>>",
      "to": "<persona email>",
      "subject": "...",
      "snippet": "<first 100 chars or so>",
      "body": "<full plausible email body, 1–6 sentences for transactional, longer for personal>",
      "labels": ["INBOX", ...],
      "received_at": "<ISO 8601 with +05:30 timezone>"
    }
  ]
}
```

**Coverage required** — the mailbox must contain signal that each of these 8 sub-agents could plausibly act on. Aim for the rough counts below per persona:

| Sub-agent             | What kind of email                                                                                                                   | Count target           |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------------------- |
| Calendar / Scheduling | Meeting invites, RSVP requests, reschedules                                                                                          | 4–8                    |
| Email triage          | Personal mail needing reply, recruiter outreach, threads with commitments ("I'll send you X by Friday")                              | 8–12                   |
| Food & order-history  | Swiggy / Zomato / Blinkit / Instamart confirmations — must show **recurring patterns** (e.g. Aditi orders Meghana's most Wednesdays) | 12–20                  |
| Travel                | Flight/hotel/cab bookings, web check-in reminders, itineraries, status changes                                                       | 4–8 (across 2–3 trips) |
| Bills & finance       | Monthly bill cycles (electricity 12x, mobile 12x), credit card statements, subscription renewals, refund threads                     | 15–25                  |
| Dates & relationships | Birthday-related emails, e-card services, gift confirmations from past dates                                                         | 2–4                    |
| Shopping & wishlist   | Order confirmations, wishlist-item-back-in-stock, sale notifications, price-drop alerts                                              | 5–10                   |
| To-dos & commitments  | Action items captured in email threads (project deadlines, "let's catch up", forms to fill)                                          | 4–8                    |

**Realism rules:**

- Sender domains must look real: `noreply@swiggy.in`, `bills@bescom.co.in`, `team@razorpay.com`, `notifications@indigo.in`, `statements@hdfcbank.net`.
- Recurring patterns must actually recur — Aditi's Meghana's order should appear ~30+ times across the year on Wednesdays around 14:00, not 3 random times. Devendra's BESCOM bill should appear monthly on a consistent day-of-month.
- Bodies should be plausible. Bill emails name an amount and due date. Order confirmations name the items, restaurant, and total. Personal emails sound human.
- `received_at` timestamps must be realistic for the email type (Swiggy at lunch/dinner times, bills early morning, personal mail variable).
- IDs should be unique (`msg_001` … `msg_092`). Threads should group related emails (a flight booking + check-in reminder share a thread_id).
- For Arjun and Meera (first-run, onboarded 2026-05-01) — their mailbox still spans the full year; the assistant just hasn't seen them yet. Their first run will mine this history for backfill.

---

## File: `calendar.json`

Calendar spanning roughly **2025-11-01 → 2026-11-01**. Density: **30–60 events per persona**.

**Schema:**

```json
{
  "events": [
    {
      "id": "evt_001",
      "summary": "...",
      "start": "<ISO 8601 with +05:30, or YYYY-MM-DD if all_day=true>",
      "end": "<ISO 8601 with +05:30, or YYYY-MM-DD if all_day=true>",
      "location": "<address or 'Google Meet' or empty string>",
      "attendees": ["email1", "email2"],
      "description": "<optional notes>",
      "all_day": false
    }
  ]
}
```

**Coverage required:**

- Recurring weekly events from the persona's profile (Aditi's pottery class Saturdays, sprint planning Tuesdays, etc.) — show ~8–12 instances of each, not 52.
- Birthdays of important people from the profile as `all_day: true` events on the right dates.
- Festivals the persona observes (Diwali, Holi for Aditi/Devendra; Durga Puja for Arjun; Onam for Meera) on correct 2025/2026 dates.
- 1–2 trips that line up with the mailbox — block the destination dates as `all_day: true` events ("Bali — Aditi + Mom").
- A few 1:1s, doctor visits, school events (for Arjun's kids), client meetings (for Devendra), hospital shifts (for Meera).
- Today (2026-05-01) and the next ~7 days should be **populated** — this is what the cron sees and acts on.

---

## File: `fixtures/2026-05-01.json`

The cron payload for today's run.

**Schema:**

```json
{
  "date": "2026-05-01",
  "user_slug": "<slug>",
  "gmail": [
    /* email objects, slice of mailbox where received_at is on 2026-04-30 */
  ],
  "calendar": [
    /* event objects, slice of calendar where event falls between 2026-05-01 and 2026-05-07 */
  ]
}
```

The `gmail` array = subset of `mailbox.json` filtered to **received_at on 2026-04-30** (yesterday's overnight slice). Aim for 5–10 emails — the kind of stuff that piles up in 24 hours.

The `calendar` array = subset of `calendar.json` for events between **2026-05-01 (today) and 2026-05-07 (one week ahead)**. Aim for 6–15 events.

The fixture must be **internally consistent with mailbox.json + calendar.json** — same IDs, same content. It is a slice, not a separate dataset.

---

## Final acceptance checklist

For each persona:

- [ ] `meta.json` valid, `onboarded_at` matches the table above.
- [ ] `profile.md` covers all 12 sections, ≥10 important dates, partner + family + friends with gifting cues.
- [ ] `mailbox.json` has 60–100 messages spanning 2025-05-01 → 2026-04-30, hits all 8 sub-agent coverage targets, recurring patterns actually recur.
- [ ] `calendar.json` has 30–60 events spanning ~Nov 2025 → Nov 2026, today's week is populated.
- [ ] `fixtures/2026-05-01.json` is a consistent slice of mailbox + calendar, not a fresh fabrication.
- [ ] `avatar.png` matches the persona description.
- [ ] City-specific brands/places used (BESCOM for Bangalore, Torrent Power for Ahmedabad, Adani Electricity for Mumbai, CESC for Kolkata).
- [ ] Names of people in the persona's life are culturally consistent.
- [ ] No placeholder text, no `lorem ipsum`, no generic "Test Email 1" subjects.

# LLM Judge — events specifics

The agent under evaluation surfaces concert / show / festival actions for the artists, venues, traditions, and circuits the user's profile already says they care about. Its hardest property is **specificity**: most days legitimately produce zero output, and the dominant failure modes are (a) treating any inbound personal email as an event task, (b) speculating about profile-named artists with no live announced show, and (c) surfacing events well outside their lead window.

## Agent's stated scope

The events agent owns exactly four kinds of action — every actual task must reduce to one of these, with the action verb starting with `Buy tickets for ...`, `Tickets open ...`, `Lineup update — ...`, or `Save the date for ...`:

1. **Sale-window nudge — `Buy tickets for ...`** — A specific show by a profile-named artist / festival / tradition is on sale RIGHT NOW (verified via a ticket-platform email in today's slice or a `web_search`-confirmed live sale). Includes city sanity: the show is in a city the user lives in or has confirmed travel to.
2. **Tickets-open countdown — `Tickets open ...`** — A specific sale-open moment is announced for a profile-named artist's show; the nudge fires shortly before sale-open so the user can buy fast.
3. **Festival lineup update — `Lineup update — ...`** — A festival the user is already considering / annually attends added a profile-named artist to its lineup. ONE re-nudge per real lineup change.
4. **Save-the-date free event — `Save the date for ...`** — A free-entry, profile-aligned cultural / civic / hobby / religious event with a fixed announced date that the user would want on their radar (Tagore tributes for a Rabindra-Sangeet listener, Durga Puja sabha sessions for a Bengali persona, coin-fair / numismatics meets for a numismatics hobbyist, Sahitya Parishad lectures, Paryushan discourses, alma-mater fest free sessions). No ticket = no `Buy tickets`; the action is to put it on the calendar early.

A profile-named artist with no live announced show today is NOT a task. A live ticket signal for an artist not in the profile is NOT a task. **Both halves are required, every time.**

Out-of-scope (each is **another agent's lane** or non-actionable):

- Existing concert events already on the calendar — leave-now / prep / post-event are **calendar** agent's lane.
- Replying to a ticket-platform email or to a social invitation → **email_triage**.
- Birthday / anniversary / festival GIFTING → **dates** (and the gift purchase itself → **shopping**).
- Trip-blocks / flight bookings / hotel itineraries / destination-prep exhibitions during a booked trip → **travel** (the events agent only owns ticketed performances + profile-aligned free cultural events, not generic destination-prep).
- Bills / subscriptions / payment portals → **finance**.
- Food / restaurant plans → **food**.
- Spousal / friend / family social-coordination invites (bridge games, brunches, weddings without a ticketed performance) → **email_triage**.
- Generic ticket-platform digests with no profile-named artist hit → skip.
- Speculative "you might like" suggestions for artists / venues not named in the profile → skip.
- Pre-registration / ballot signups for tournaments where ticket sale is not yet open → skip until real sale opens.

## Common failure modes — flag these strictly

Treat the following as **skip violations** even when the agent dressed them up in an allowed verb prefix:

- **Inbound personal email reframed as an event task.** Sudipto's bridge invite turned into `Buy tickets for Sudipto bridge Saturday`; Mitali's breakfast email turned into `Lineup update — Sunday breakfast at Flurys`; Mom's check-in turned into any events shape. Lane error — skip.
- **Admin / FYI / work email reframed as an event task.** HR holiday FYI turned into a `Save the date for ...`; Dad's insurance email turned into `Buy tickets for ...`; Nilesh's audit email turned into any events shape. Skip.
- **Speculative artist task with no live signal.** `Buy tickets for Frank Ocean ...`, `Buy tickets for AP Dhillon arena show ...`, `Buy tickets for Kishori Amonkar tribute concert ...`, `Watch for Coldplay India 2027` — profile-named artist but no announced 2026 show in the user's window. Skip.
- **Event concluded / past-the-window already.** `Buy tickets for Anuv Jain Dastakhat Mumbai` after the Mumbai date concluded; `Buy tickets for Lifafa Mumbai Apr 4` after the date passed. Skip.
- **Sale not yet open dressed up as `Buy tickets for ...`.** The signal is "announced — dates pending" / "tentative dates" / "ballot opens 12 months out" — that is NOT a sale-window nudge. The correct fire is `Tickets open ...` ONLY when there is a concrete sale-open time; until then, skip.
- **Festival lineup update with no profile-named artist on the bill.** `Lineup update — Summer Sonic Tokyo` when none of the user's profile-named artists are announced. Skip.
- **Event outside the lead window.** `Lineup update — Mood Indigo 2026` fired in May (festival is in December); `Lineup update — Sunburn Mumbai Dec 2026` fired in May; `Tickets open for Dover Lane 2027` fired in May (sale opens late December). Skip.
- **Wrong-city show with no travel anchor.** A Delhi-only show for a Bangalore-based persona with no Delhi trip on the calendar; a US-only AP Dhillon arena show for a persona with no US travel. Skip.
- **Duplication of another lane.** A cricket match the persona has already booked on their July London itinerary re-surfaced as `Buy tickets for ...` — that match is calendar/travel; only ADJACENT cricket events at the same trip qualify. Skip.
- **Free art-exhibition / destination-prep during a booked trip dressed up as `Buy tickets for ...`.** Free DAG exhibition during a Mumbai trip, free museum visit during a Japan trip — destination-prep is travel's lane, not events. Skip.
- **Wrong action verb.** `Reply ...`, `Send ...`, `Plan ...`, `Schedule ...`, `Block ...`, `Set a reminder ...`, `Watch for ...`, `Track ...`, `Note ...`, `Confirm ...`, `Suggest ...`, `Check ...`, `Look up ...`, `Look for ...`, `Book ...`, `Reserve ...`, `Order ...`, `Pick up ...`, `Surface ...`, `Remind ...`, `Get ...`. None are events shapes. Mark `unexpected` and call out the verb in `reasoning`.
- **Filler / vague tasks.** `Plan a concert outing`, `Track artist tours`, `Browse upcoming shows in Bangalore` — no specific show + artist + city + date. Mark `unexpected`.
- **Echoing the profile back as preference_updates.** `User loves Anuv Jain` / `User has been to Coldplay` / `User prefers indie music` are already in the profile. Credit a preference_update only when it adds an evidenced new datum — a discovered ticket-platform preference (e.g. "uses District 80% of the time"), an annual festival-circuit pattern, a city circuit, or a new favourite artist evidenced by 2+ ticket purchases the profile doesn't list yet.
- **Off-lane preference_update sections.** Any `preference_update` with `section` ∈ `{"Food", "Bills & Subscriptions", "Travel", "Relationships", "Schedule", "Commitments style", "Shopping", "Communication preferences"}` is a lane error — those belong to other agents. Only `Events` and `Music & Hobbies` are valid sections for this agent.

## Borderline calls — use these heuristics

- **`Save the date for ...` for a free event months out.** The event is free-entry, profile-aligned, and on a fixed announced date that won't move (Tagore-anniversary tributes, Durga Puja sabha, Paryushan discourses, annual coin fair). One early `Save the date for ...` is in scope even if more than 14 days out, BECAUSE there is no sale window to wait for and the user's value is "have it on my calendar." Do NOT extend this generosity to ticketed shows — those need a real sale window.
- **Profile-only persona (e.g. Meera) BACKFILL with no Gmail/Calendar OAuth.** Tasks may still be valid IF they are grounded in `web_search`-verified live sales for profile-named artists in the user's home city / travel city. The absence of mailbox does NOT mean silence is automatic — `web_search` discovery against profile-named artists in a real sale window is fair game. Penalise both: (a) silence when a clear web-verified profile-anchored show exists; (b) speculative tasks for artists with no announced 2026 show.
- **Bucket-list artist with a non-sale signal.** Profile says "would fly anywhere in Asia for Kendrick" + a leak says "KL date announced — sale TBD". The correct fire is `Tickets open ...` ONLY when a concrete sale time is announced; before that, even high intent is not a `Buy tickets for ...`. A `Buy tickets for Kendrick KL` fired today on dates-pending info is a skip violation.
- **Show in the user's regional travel orbit (Bali → Singapore / KL hop, London → adjacent cricket events).** Reachable cities during a booked trip ARE valid city anchors for `Buy tickets for ...` — credit when the artist is profile-named and the sale is live.
- **`web_search` companion to profile-named artist.** A `web_search`-verified live ticket page on a credible platform (BookMyShow, District, Paytm Insider, Skillbox, Ticketmaster Asia, NCPA, NOL World, Lord's, ECB Tickets, Visva-Bharati, official festival site) is a valid trigger even without an email companion — one solid trigger is enough; the rationale must name the source.
- **BACKFILL preference_updates with quantitative grounding.** "User attended Bacardi NH7 Pune in 2024 and 2025 — likely annual circuit" or "District is the user's go-to ticket platform — 4 of 5 confirmations from District" are gold-standard. Plain restatements of profile artists are wrong. For profile-only personas (no Gmail/Calendar OAuth), echoing profile artists back is **wrong** — mark those preference_updates as failing the topic match.

## Surface-time check (ancillary, not blocking)

Events tasks should carry an ISO 8601 `suggested_surface_time` anchored to a real moment:

- `Buy tickets for ...` → as soon as the sale-open is verified (today, ideally within working hours).
- `Tickets open ...` → 2–6 hours before the announced sale-open time.
- `Lineup update — ...` → the day the lineup change is announced.
- `Save the date for ...` → 7–14 days before the event for prep, OR earlier (one early heads-up) for once-a-year fixed-date cultural events the user reliably attends.

A task with a non-ISO surface time (`"morning"` / `"later"` / `"this weekend"`) is a quality flag — note it in `reasoning` for the matched alignment but do not auto-fail the alignment.

## Silence is correct

When `expected_tasks` is empty, the agent should produce zero tasks. Each surfaced task in that case is at minimum an unexpected FP, and if it matches an expected_skip it's a skip violation. **Silence on a no-trigger day is the right answer**, especially when:

- The slice has no ticket-platform / artist-newsletter / sale-open email.
- No profile-named artist has an announced live show in the user's window or city.
- The historical mailbox (BACKFILL) has no ticket / festival cadence to mine.
- The persona has not granted Gmail/Calendar access AND `web_search` returns no profile-named artist sales in the window.

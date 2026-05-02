# LLM Judge — calendar specifics

The agent under evaluation surfaces calendar / scheduling actions for a person's day. Its hardest property is **specificity**: most days legitimately produce zero calendar action, and the dominant failure mode is filler. Be strict.

## Agent's stated scope

The calendar agent owns exactly five kinds of action — every actual task must reduce to one of these:

1. **Prep nudge** — review materials / read a deck / pull notes before a meeting that's about to start.
2. **Leave-now alert** — travel-time-driven "leave by HH:MM" for an event with a real location and non-trivial commute.
3. **Conflict flag** — two events overlap, or a new event collides with a stated routine in the profile (Sun yoga, Fri date night, family dinner, sitar lesson, Paryushan, etc.).
4. **RSVP pending** — an invite the user hasn't responded to and the event is approaching.
5. **Post-event follow-up** — send notes / share recording / next steps after a meeting that just ended.

Out-of-scope (each is **another agent's lane**):

- Bill / insurance / subscription due-dates → **finance**.
- Birthday / anniversary / occasion reminders → **dates**.
- Trip-block events, web check-in, cab-to-airport, hotel itineraries → **travel**.
- Food-order suggestions ("order Meghana's at 1:30pm") → **food**.
- "Reply to this email" / drafting responses → **email_triage**.
- Generic to-dos and self-made commitments → **todos**.

## Common failure modes — flag these strictly

Mark these as **skip violations** even when the agent dressed them up as calendar-shaped tasks:

- **Admin email reframed as a calendar reminder.** "Set a reminder to renew ICICI Lombard insurance" / "Block May 7 in calendar to pay BESCOM" — the underlying task is finance, the calendar wrapper does not change the lane.
- **FYI announcements blocked into the calendar.** HR holiday emails, public-holiday notices, "office closed" emails — these are not events that need any action.
- **Inbound social/work coordination pre-created as events.** "Bridge Saturday — confirm with Sudipto" or "Discuss audit tomorrow with Nilesh" — when the time has not actually been agreed, the event does not yet exist; replying-to-coordinate is email_triage. Pre-creating speculative calendar events is a hallmark calendar-agent failure.
- **Filler reminders for established recurring routines.** A bare "Saturday 4pm pottery class" or "Sunday 8am yoga" reminder is filler if there is no specific reason (no prep, no leave-by, no conflict). Established routines in the profile do not need passive reminders that just restate the calendar.
- **Outside-window leave-now / prep alerts.** A leave-by alert for Tuesday's 11am meeting fired on the previous Friday is wrong — leave-now alerts fire on the day, 5–15 min before the leave-by time. Same for prep nudges (30–60 min before, on the day).
- **Walking-distance leave-now alerts.** If the profile states the venue is walking distance (Aditi → Toit / Glen's Indiranagar; Arjun → Park Street; Meera → KEM ward block), there is no travel-time computation that justifies a leave-now alert.
- **Hallucinated tasks for personas with no calendar input.** When `actual_tasks` references events that don't exist in the slice, that's an unexpected (FP) output.
- **Multiple tasks for the same event.** Each event surfaces at most one action; "prep for sprint planning" + "leave for sprint planning" + "review sprint backlog" for the same event is duplication.

## Borderline calls — use these heuristics

- **Routine event vs notable event.** A weekly recurring meeting is generally filler unless: there's a specific prep request in the inbox, a new conflict, a venue change, or it crosses a stated routine boundary. Reward the agent for finding the *non-obvious* signal in a routine; do not reward bare reminders.
- **Email mentions a time → does it deserve a calendar task?** Only if (a) a calendar event already exists referencing that thread, or (b) the email IS a formal invite and an RSVP is missing. Vague "let's discuss tomorrow" emails are email_triage, not calendar — count as skip violation if surfaced as a calendar block.
- **Travel-time alert for a known venue.** Reward if the profile or prior context establishes the commute is non-trivial (e.g. Indiranagar → Embassy Tech Village ~25 min, Bodakdev → Ashram Road traffic-dependent). Penalise if the venue is profile-stated walking distance or the agent fabricated a travel time without evidence.
- **Conflict with stated routine.** A meeting that overlaps Sun yoga / Fri date night / Sun family dinner / Paryushan / sitar lesson / weekly pottery is in scope as a conflict_flag, even if the calendar event itself is not "double-booked" in the technical sense — the profile-stated routine counts as the second event.
- **Backfill mode + empty calendar history.** If `calendar.json` is empty for a backfill persona, expected_preference_topics will typically be empty too — the agent should NOT echo profile-stated routines back as preference updates. Reward silence; do not reward "summarised the profile."

## Surface-time check (ancillary, not blocking)

Calendar tasks should carry ISO 8601 `suggested_surface_time` anchored to a real moment. Per the agent's prompt:

- **leave_now_alert** → 5–15 min before computed leave-by time.
- **prep_nudge** → 30–60 min before the meeting starts.
- **rsvp_pending** → anytime before event start; ideally 24h+ ahead.
- **post_event_followup** → within a few hours after the event ends.
- **status_change** → as soon as the source mail arrives.

A task with the wrong category-window (e.g. a leave-now alert scheduled 2 hours before the meeting) is not a hard skip violation, but call it out in `reasoning` for the matched alignment so the harness can see surface-time drift. A task with a non-ISO time string ("morning", "later", "9am default") is a quality flag — note it but do not auto-fail the alignment.

## Silence is correct

When `expected_tasks` is empty, the agent should generally produce zero tasks. Each surfaced task in that case is at minimum an unexpected FP, and if it matches an expected_skip it's a skip violation. **Silence on a no-action day is the right answer**, and the harness rewards it via `precision = recall = 1.0` when both expected and actual are empty.

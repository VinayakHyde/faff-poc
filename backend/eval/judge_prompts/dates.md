# LLM Judge — dates specifics

The agent under evaluation surfaces dates / occasions / relationships actions for a person's day: birthday and anniversary reminders with a concrete gift or message suggestion, festival reminders, and "reach out to X" nudges for profile-listed close contacts who have gone quiet. Its hardest property is **specificity**: most days legitimately produce zero output, and the dominant failure mode is reframing inbound personal emails as relationship tasks or surfacing dates that are too far in the future.

## Agent's stated scope

The dates agent owns exactly three kinds of action — every actual task must reduce to one of these, with the action verb starting with `Wish ...`, `Order gift for ...`, or `Reach out to ...`:

1. **Birthday / anniversary / death-anniversary reminder** — a profile-stated person's date falls inside the lead window today (5–7 days before for local gifts, 7–10 days before for international, 1–2 days before for message-only / death anniversary). Each task includes a specific gift idea or message angle keyed off profile cues.
2. **"Reach out to X" — relationship-revival nudge** — a profile-listed close contact (close friend, mentor, family flagged as "people to keep in touch with") whose last evidenced Gmail/Calendar contact exceeds the relationship's natural cadence (4+ months for quarterly pairs, 3+ months for monthly+ ones). Replying to an inbound message from such a contact is NOT a "reach out" task — that's email_triage's lane.
3. **Festival / cultural-occasion reminder** — a festival the profile **explicitly says the user celebrates**, falling inside the lead window (7–10 days before for prep / sweets / decor; 1–2 days for message-only).

Out-of-scope (each is **another agent's lane**):

- Replying to inbound personal email → **email_triage**.
- Buying the actual gift / placing the order → **shopping** (dates only flags the suggestion).
- Booking an anniversary dinner reservation → **food** / **travel**.
- Bills / insurance / subscription due-dates → **finance**.
- Trip-block events / web check-in → **travel**.
- Self-marker dates that don't involve another person (e.g. residency joining anniversary, work joining anniversary) → not a date-agent task.
- Festivals NOT named in the persona's profile.

## Common failure modes — flag these strictly

Treat the following as **skip violations** even when the agent dressed them up as `Wish ...` / `Order gift for ...` / `Reach out to ...` shaped tasks:

- **Inbound personal email reframed as "Reach out to X".** Mom emailed today → agent surfaces "Reach out to Mom — she said she's missing you." The trigger is the email, not silence; replying belongs to email_triage. Skip.
- **Inbound spousal / friend invitation reframed as a relationship task.** Sudipto / Mitali / Karan emails an invite — agent surfaces "Reach out to ..." or "Wish ... about plans." Same lane error. Skip.
- **Admin / work / FYI email reframed as a date task.** Dad's insurance renewal turned into "Wish dad about insurance"; HR holiday FYI turned into "Wish team happy Labor Day"; Nilesh's audit email turned into "Reach out to Nilesh" — all out of lane. Skip.
- **Date surfaced too far before its lead window.** Mom's birthday in 4 months surfaced today; an anniversary 2 months out surfaced today; Diwali surfaced in May. The agent's value is hitting the right window — earlier is padding. Skip.
- **Belated wishes / belated festival greetings.** Birthday 5+ days past; festival a week past. Belated nudges are not the agent's job — the moment passed. Skip.
- **Self-marker dates surfaced as relational tasks.** Residency joining anniversary, work-iversary, or other self-only dates do not fit any of the three categories. Skip.
- **Festival not on the persona's profile.** Karva Chauth surfaced for a persona who doesn't observe it; Durga Puja surfaced for a non-Bengali persona; Onam for someone who doesn't celebrate it. Skip.
- **Filler / vague tasks.** "Plan something for the weekend", "Remind user that Diwali is coming", "Call someone you miss" — no specific person + date + suggestion. Mark unexpected (FP).
- **Wrong action verb.** `Send ...`, `Buy ...`, `Plan ...`, `Schedule ...`, `Reply ...`, `Remind ...`, `Block ...`, `Set a reminder ...`, `Note ...`, `Confirm ...`, `Track ...`, `Follow up ...`, `Check ...`, `Look up ...`, `Book ...`, `Reserve ...`, `Suggest ...`, `Draft ...` — none are date-agent shapes. Mark unexpected.
- **Diet / cultural-violation suggestions.** Suggesting non-veg or onion/garlic gifts to a strict-Jain persona; suggesting a steak dinner reservation for a vegetarian; ignoring Paryushan austerity for the period it covers. Treat as a skip-shaped failure even if no expected_skip lists it specifically — call it out in `reasoning` and mark `unexpected`.
- **Echoing the profile back as preference_updates.** A `preference_update` that just restates a profile bullet ("Mom's birthday is August 23") with no quantitative grounding from email / calendar evidence is borderline filler. Credit only when the update adds a NEW datum (last year's gift store, observed cadence, a person not in the profile) OR when it's a faithful capture of the date+gifting cue during BACKFILL of a freshly-onboarded persona who has email/calendar evidence to mine. For profile-only personas (no Gmail/Calendar OAuth), echoing profile dates back is **wrong** — mark those preference_updates as failing the topic match and flag it.

## Borderline calls — use these heuristics

- **Profile-only persona (e.g. Meera) BACKFILL.** The profile already encodes every important date. Empty Gmail / Calendar means there's no evidence to ground a quantitative preference_update. Reward silence on BOTH tasks and preference_updates. Penalise any echo of profile dates as a discovery.
- **Date inside lead window vs slightly outside.** A birthday at exactly 7 days out is the edge of the local-gift window — credit. A birthday 8–10 days out is outside the local window but inside the international window — credit only if the recipient is international. A birthday 14+ days out is outside any gift window — skip / unexpected.
- **Recurring all-day calendar event for a profile-listed birthday.** Same evaluation as the profile date itself. The calendar event is a confirmation, not a duplicate trigger.
- **"Reach out" nudge for someone in active inbox contact.** If gmail_search shows correspondence with the contact in the last 30 days, "reach out" is wrong — they're in touch. Skip. If gmail_search shows 4+ months of silence for a profile-listed quarterly contact, "reach out" is in scope.
- **BACKFILL preference_update with quantitative grounding.** "Mom Sunita's birthday Aug 23 — last year (per gmail) ordered tuberose via Ferns N Petals on Aug 19" is the gold standard. Plain "Mom's birthday is Aug 23" is borderline; credit during BACKFILL of an OAuth-granted persona only as a faithful capture of date + gifting cue.

## Surface-time check (ancillary, not blocking)

Dates tasks should carry an ISO 8601 `suggested_surface_time` anchored to a real moment:

- **Order gift for ...** → 5–7 days before the date (7–10 for international); the surface_time should land in the morning of the lead-day so the user has the day to act.
- **Wish ...** → 1–2 days before, or the morning of the date itself.
- **Reach out to ...** → anytime in the day the agent fires; ideally morning so the user has the day to send the note.
- **Festival prep / message** → per the festival's lead window.

A task with a non-ISO surface time (`"morning"` / `"later"` / `"in a few days"`) is a quality flag — note it in `reasoning` for the matched alignment but do not auto-fail the alignment. A task whose surface_time is dramatically off-window (e.g. a `Wish` 30 days early) IS a quality issue worth recording.

## Silence is correct

When `expected_tasks` is empty, the agent should generally produce zero tasks. Each surfaced task in that case is at minimum an unexpected FP, and if it matches an expected_skip it's a skip violation. **Silence on a no-action day is the right answer**, especially when:

- No profile-stated date falls inside today's lead window.
- All inbound personal emails belong to email_triage.
- Profile-listed close contacts are all in active inbox contact (so no "reach out" trigger).
- The persona is profile-only with no Gmail / Calendar OAuth — and no profile date hits today's window.

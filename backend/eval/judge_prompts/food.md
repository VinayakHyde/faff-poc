# LLM Judge — food specifics

The agent under evaluation surfaces food-and-grocery actions for a person's day: recurring delivery orders, staple restocks, mealtime-gap nudges, and new-restaurant suggestions. Its hardest property is **specificity**: most days produce zero food action, and the dominant failure is treating any email that mentions food as a trigger to order something.

## Agent's stated scope

The food agent owns exactly four kinds of action — every actual task must reduce to one of these, with the action verb starting with `Order ...` or `Restock ...`:

1. **Recurring food order** — a profile- or email-evidenced order that repeats on a stable day-of-week + time and is firing today / in the next ~24h.
2. **Staple restock** — a pantry/grocery item the user buys repeatedly via Instamart-style apps and is now due based on a real cadence (last-order date + average gap).
3. **Mealtime-gap nudge** — a calendar gap today aligned with lunch/dinner that maps to a profile-stated venue or recurring dish.
4. **New-restaurant / new-favourite** — a verified new opening matching the user's stated wishlist or a place tried 2+ times in the last month, supported by `web_search` evidence.

Out-of-scope (each is **another agent's lane**):

- Replying to spouse / friends about meal plans → **email_triage**.
- Replying to Swiggy customer service → **email_triage**.
- Paying Swiggy One / food-app subscription bills → **finance**.
- Booking dine-in reservations for an occasion → **dates** flags the occasion; food only handles the actual delivery order.
- Calendar reminders for a meal that's already scheduled → **calendar**.

## Common failure modes — flag these strictly

Treat the following as **skip violations** even when the agent dressed them up as `Order ...` / `Restock ...` shaped tasks:

- **Personal email mentioning a food brand reframed as an order.** A spouse / friend / family member emails "Flurys this Sunday?" — the food agent must NOT convert this into `Order Flurys for Sunday`. The Sunday Flurys order is triggered by the recurring pattern on Sunday morning, not by the social email today. The social reply is email_triage's lane. Surfacing the order on the wrong day off the back of a social email is a skip violation.
- **Out-of-lane content rephrased into a food action.** Mom's "hope you are eating well" check-in turned into `Order something nourishing` — the email is relational, not a food trigger. HR's "enjoy the long weekend" turned into `Order takeaway` — holiday FYI is not a food trigger. Dad's insurance email turned into anything food-shaped — clearly out.
- **Profile-only restock with no email cadence.** `Restock oat milk via Instamart` for a persona whose mailbox has zero Instamart confirmations — the agent invented a cadence from a profile bullet. Skip violation.
- **Recurring nudge fired multiple days early.** The Wednesday Meghana's biryani slot surfaced on Friday is wrong — recurring nudges fire ~30 min before the slot, not days ahead.
- **Reservation already on the calendar, agent suggests an order anyway.** Date-night Toit booked at 20:00 → agent surfaces `Order ahead from Toit` or `Order something for date night.` Toit is dine-in; the dinner is settled. Skip.
- **Filler / vague nudges.** `Order lunch`, `You haven't eaten yet today`, `Try a new restaurant this weekend` — no specific dish + restaurant + time. Not a valid food task.
- **Wrong action verb.** `Plan Sunday breakfast`, `Suggest dinner ideas`, `Reply to Mitali about brunch`, `Confirm with Karan about Friday` — these are not `Order` / `Restock`, so they are not food-domain tasks.
- **Hallucinated tasks for personas with no food signal AND no firing profile pattern.** When today is e.g. a Monday and the profile has no Monday food pattern, surfacing a Monday lunch order with no email or calendar anchor is unexpected (FP).
- **Diet-violating suggestions.** Suggesting non-veg or onion/garlic dishes to a strict-Jain persona; suggesting meat to a persona who is in a stated vegetarian / pescatarian phase. Treat as a skip-shaped failure even if no expected_skip lists it specifically — call it out in `reasoning` and mark the task `unexpected`.

## Borderline calls — use these heuristics

- **Profile pattern + already-on-calendar.** If the profile recurring slot is already represented as a calendar event the user themselves created (e.g. "Sunday Brunch at Glen's" already booked), the food agent does NOT need to also surface an order — the meal is settled. Surfacing a duplicate is unexpected (FP), not a hard skip violation unless an expected_skip names it.
- **BACKFILL preference_updates that restate the profile.** When the profile narrative already names a recurring restaurant/day, an email-mined preference update with **quantitative confidence** (order count, average gap, exact time) is still useful and counts as a topic hit. A bare restatement of the profile bullet ("user likes Flurys on Sundays") with no order-history grounding is borderline — credit only if it captures the email-evidenced cadence.
- **Mealtime gap on a holiday with no profile pattern.** Today being a public holiday does not by itself constitute a "calendar gap" trigger. Without a profile-stated venue for that meal/day, surfacing a generic holiday-meal nudge is unexpected (FP).
- **Spouse mentions a food brand AND the day-of-week pattern fires.** If today is the actual day the recurring pattern fires (e.g. spouse emails Sunday morning about Flurys AND the Sunday-9am Flurys pattern is in profile), then surfacing the order is fine — the trigger is the recurring pattern, not the email. But on any other day-of-week, the email alone is not a trigger.

## Surface-time check (ancillary, not blocking)

Food tasks should carry an ISO 8601 `suggested_surface_time` anchored to a real moment:

- **Order (lunch)** → 30 min before lunchtime (~12:30 for a 13:00 meal).
- **Order (dinner)** → 30–45 min before dinnertime.
- **Restock** → morning of the due-day, before the user starts their workday.

A task with a non-ISO surface time (`"morning"` / `"later"` / `"around lunch"`) is a quality flag — note it in `reasoning` for the matched alignment but do not auto-fail the alignment.

## Silence is correct

When `expected_tasks` is empty, the agent should generally produce zero tasks. Each surfaced task in that case is at minimum an unexpected FP, and if it matches an expected_skip it's a skip violation. **Silence on a no-action day is the right answer**, especially when:

- Today's day-of-week fires no profile pattern.
- The slice has no Swiggy/Zomato/Instamart confirmation.
- The calendar-on-display is fully covered by the user's own bookings (no genuine meal gap).

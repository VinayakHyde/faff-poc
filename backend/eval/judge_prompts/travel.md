# LLM Judge — travel specifics

The agent under evaluation handles travel logistics: surfacing only the concrete pre-flight, in-trip, and arrival actions that a careful assistant would handle for an *imminent* trip — derived from a specific booking email.

## Agent's stated scope

Travel owns exactly six kinds of action, each gated by both an action-shape constraint and an imminent-window constraint:

1. **Web check-in nudges** — flight in 20–28 hours.
2. **Cab-to-airport nudges** — flight in 2–8 hours.
3. **Day-of itinerary recaps** — travel day is today.
4. **Status-change alerts** — delay / gate change / cancellation email just landed.
5. **Hotel check-in / check-out reminders** — stay is today or tomorrow.
6. **Destination prep** — arrival at non-home destination in next 24–36 hours.

Out-of-scope: tasks invented from profile mentions alone (no booking email), tasks for past trips, tasks for trips outside the imminent windows above (a flight 5 weeks away, a hotel 2 months out), generic trip-planning suggestions, calendar-blocking the trip dates (that's the calendar agent's domain), credit-card bills for the flight (finance), personal mails about the trip (email_triage).

## Common failure modes — flag these strictly

Treat the following as **skip violations** even if the agent dressed them up under a permitted action verb:

- **Premature hotel/flight nudges** — surfacing "Hotel check-in" or "Web check-in" or "Destination prep" for a stay/flight that is weeks or months away. Examples to flag: "Hotel check-in for Taj Mahal Palace Mumbai" when stay is 40 days out; "Web check-in for Bali" when flight is 10 weeks out; "Destination prep for Bali" when arrival is in July and today is May.
- **Past-trip resurfacing** — surfacing any task tied to a flight or hotel that has already concluded (e.g. "Itinerary recap for BLR→PNY" when that flight was in February).
- **Profile-only tasks** — surfacing a travel task purely because the profile mentions an upcoming trip (e.g. "Web check-in for Japan flight" when the profile lists October 2026 but no ticket email exists). Required source is a booking email.
- **Verb-rewordings of out-of-scope work** — "Plan packing list", "Set a reminder to book cab someday", "Note the trip dates", "Buy travel insurance", "Schedule airport pickup". The action verb must be one of the six allowed shapes AND the underlying signal must be in-window.
- **Duplicates for the same booking** — three separate "web check-in" tasks for the same flight, or both a "hotel check-in" and a generic "trip reminder" for the same stay.
- **Generic destination prep** — "Explore Bali highlights" with no profile-specific tie-in (cuisine, dietary, interest). Out.

## Borderline calls — use these heuristics

- **Booking email exists but the date is ambiguous (no day in body):** if the agent cannot confidently place the trip inside an imminent window, silence is correct. Surfacing a guess about timing counts as `unexpected`.
- **Calendar block exists but no booking email:** for example, the calendar shows "Bali Trip" for July 12-19 but only a hotel email exists, no flight email yet. The hotel itself is months away → still out of window. Skip.
- **A status-change email about a future trip:** even if the trip itself is weeks away, a *just-landed delay/cancellation email* IS in scope (status-change category) — the trigger is the email arrival, not the trip date.
- **Backfill preference_updates:** these are NOT tasks. Mining 12 months of history for "home airport is CCU" or "preferred airline is IndiGo" is correct BACKFILL behaviour and does not violate the booking-email constraint (those are pattern observations, not user-facing tasks).

## Surface-time check (ancillary, not blocking)

Travel tasks should carry an ISO 8601 `suggested_surface_time` aligned to the right window (e.g. T-24h for web check-in, T-2h for domestic cab, morning-of for itinerary recap, immediate for status changes). Tasks with `"morning"` / `"later"` / `"before flight"` are quality flags — note them in `reasoning` if you see them; they're not skip violations on their own.

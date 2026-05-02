# LLM Judge — finance specifics

The agent under evaluation surfaces money-related actions for a person's day — bills due, trials about to convert, subscriptions about to renew that the user might want to cancel, refunds that have stalled, and unfiled work reimbursements. Its hardest property is **specificity**: most days legitimately produce zero finance action because last cycle's bills are paid and this cycle's haven't arrived yet, OR because everything in the slice is autopay.

## Agent's stated scope

The finance agent owns exactly five kinds of action — every actual task must reduce to one of these:

1. **Bill due nudge** — utility / postpaid / manual-pay subscription / insurance / tax / professional-subscription bill arrived in inbox AND due ≤ ~10 days AND profile shows the account is manually paid (no autopay).
2. **Trial-ending nudge** — free trial converts to paid in the next 24–72h.
3. **Subscription renewal cancel-prompt** — paid renewal approaching AND profile carries an explicit low-usage / "considering dropping" cue.
4. **Refund follow-up** — promised refund stalled > 7 days with no credit-confirmation email in inbox.
5. **Reimbursement filing** — work receipt in inbox AND profile flags the user as someone who drops reimbursement filing.

Out-of-scope (each is **another agent's lane**):

- Replying to a bill-flavoured email from a family member ("Reply to Dad about insurance") → **email_triage**.
- Pre-creating a calendar block for a payment date → **calendar**.
- Birthday / anniversary / gift purchase money → **dates** / **shopping**.
- Trip booking confirmations, flight tickets, hotel vouchers → **travel**.
- Recurring food / grocery orders → **food**.
- Investment newsletters, salary credits, generic FYIs → not finance's lane.

## Common failure modes — flag these strictly

Mark these as **skip violations** even when the agent dressed them up as finance-shaped tasks:

- **Autopay confirmations surfaced as Pay-X tasks.** Netflix / Spotify / Apple One / any subscription the profile explicitly flags as autopay produces an email saying "renewed" / "your invoice" — that's a receipt, not a bill. Surfacing "Pay Netflix ₹699" when profile says autopay is a hard violation.
- **Stale bills re-surfaced.** A bill from last cycle whose due date passed > ~2 days ago is no longer actionable from inbox alone (you can't tell if it was paid). Nudging on it now is filler; this cycle's bill hasn't arrived yet.
- **Profile-only tasks when an email source exists.** "Airtel ₹X due May 2" surfaced from profile cadence while a fresh April Airtel email sits unaddressed in the inbox — the agent should be using the email, not paraphrasing the profile. (Profile-only fallback is valid ONLY for the Bill due nudge category, ONLY when (a) the profile gives a hard day-of-month, (b) the next instance is within 7 days, (c) NO bill email for that provider exists, and (d) the provider is not autopay. Meera-class personas with no Gmail are the canonical case.)
- **Wrong action verb.** "Reply to Dad about the insurance renewal", "Set a reminder to pay BESCOM", "Block May 7 for the Apple invoice", "Track the BWSSB bill" — none of these are finance verbs. Allowed verbs are exactly Pay / Cancel / Follow up on refund for / File reimbursement for.
- **Off-lane content reframed as finance.** Mom's check-in, HR holiday FYI, Sudipto's bridge invitation, Nilesh's audit email, Swiggy order confirmations, flight tickets — surfacing any of these as a finance task is a hard violation.
- **Calendar or routine reminders dressed as bill nudges.** "Block 3rd of every month to check BESCOM" is a calendar-shaped recurring reminder, not a bill nudge tied to a specific email.
- **BACKFILL preference_updates that just echo the profile.** When the profile already states a provider's day-of-month and amount, simply restating it as a preference_update is filler. The bar is information observed in the inbox that adds value (stable-vs-variable, amount range, autopay-vs-manual signal observed across cycles).
- **Out-of-lane preference_updates.** Sections like "Food", "Travel", "Relationships", "Shopping" are not finance's territory. The agent should only emit preference_updates whose `section` is "Bills & Subscriptions" or similarly money-flavoured.
- **Hallucinated tasks for the no-Gmail persona.** When mailbox and fixture are empty, the only correct output is zero tasks and zero preference_updates. Any surfaced task is an FP and any surfaced preference_update is a profile-echo violation.

## Borderline calls — use these heuristics

- **Insurance / tax / professional-subscription renewals are bills.** Even when the email source is a family forward (Dad forwarding an ICICI Lombard renewal), the underlying action is a payment with a due date — finance owns it. Reward "Pay ICICI Lombard renewal..." even if the sender is a personal contact, as long as the rationale cites the renewal-notice content (not just "Dad asked").
- **Manual-pay vs autopay.** Profile is the authority. If the profile lists a subscription with "autopay" annotation, treat the renewal email as FYI. If the profile lists it without autopay, the renewal email is a payment task.
- **Subscription cancel-prompt threshold.** Reward only when the profile gives a clear cancel cue (low-usage observation, explicit "considering dropping", "haven't used in N months"). Reward silence otherwise. A speculative "you might want to cancel this" with no profile evidence is filler.
- **Refund timing.** ≤ 7 days post-promise is too early; > 7 days with no credit-confirmation email is the right surfacing window. Reward the timing nuance.
- **BACKFILL pref-coverage.** Topics describe history-observed cycles (arrival-day, amount stability, seasonal variation, autopay-vs-manual). A `preference_update` that paraphrases an observed cycle hits the topic; one that only restates a profile sentence does not.

## Surface-time check (ancillary, not blocking)

Per the agent's prompt, ISO 8601 timestamps anchored to a real moment:

- **Bill due nudge** → ~3 days before stated due date.
- **Trial-ending nudge** → 24–48h before conversion.
- **Subscription renewal cancel-prompt** → 24–72h before renewal.
- **Refund follow-up** → at the 7-day mark from the original promise.
- **Reimbursement filing** → ASAP after receipt or 2–3 days before policy deadline.

A task with the wrong timing window is not a hard skip violation — note it in `reasoning` for the matched alignment. A task with `"morning"` / `"later"` / non-ISO time is a quality flag, not an auto-fail.

## Silence is correct

When `expected_tasks` is empty, the agent should produce zero tasks. Each surfaced task in that case is at minimum an unexpected FP, and if it matches an expected_skip it's a skip violation. The harness rewards `precision = recall = 1.0` when both expected and actual are empty. Mid-month silence days, autopay-only slices, and no-Gmail personas are all legitimate zero-task outcomes.

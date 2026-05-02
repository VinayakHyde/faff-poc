# LLM Judge — shopping specifics

The agent under evaluation surfaces buy nudges for items on the user's stated wishlist when a real external trigger (sale, price drop, restock, gift handoff) makes acting now worthwhile. Its hardest property is **specificity**: most days produce zero shopping action, and the dominant failure is treating any item the user might like — or any sale email — as a reason to buy.

## Agent's stated scope

The shopping agent owns exactly three kinds of action — every actual task must reduce to one of these, with the action verb starting with `Buy ...` or `Add ... to cart`:

1. **Wishlist price drop / sale-event match** — a specific wishlist item is meaningfully cheaper today, evidenced by a sale-alert / price-drop email or a `web_search`-verified price below the user's stated threshold.
2. **Restock alert** — a previously sold-out wishlist item is back in stock, evidenced by a restock email or current retailer page.
3. **Gift purchase handoff (from dates)** — the dates worker flagged an upcoming birthday/anniversary with a specific gift idea; shopping converts it to a concrete buy with vendor, product, price, and delivery cut-off.

A wishlist item with no trigger event today is NOT a task. A trigger event with no wishlist match is NOT a task. **Both halves are required, every time.**

Out-of-scope (each is **another agent's lane** or non-actionable):

- Order confirmations and delivery FYIs for things already bought → skip / FYI.
- Food / grocery delivery → **food** agent.
- Travel bookings → **travel** agent.
- Bills / subscriptions / insurance renewals → **finance** agent.
- Birthdays / anniversaries surfaced from the profile alone (without a concrete gift idea) → **dates** agent.
- Replying to a sale-alert email → **email_triage** (rare; usually skip).
- Generic "big sale" newsletters with no wishlist match → skip.

## Common failure modes — flag these strictly

Treat the following as **skip violations** even when the agent dressed them up as `Buy ...` / `Add ... to cart` shaped tasks:

- **Profile-only nudge — wishlist item with no external trigger.** `Buy Loewe Puzzle bag — wishlist item` for a persona whose slice has no sale email, no restock email, no web_search-verified price-drop today. The wishlist alone is a filter, not a trigger. Skip violation.
- **Generic sale blast reframed as a buy.** `Buy at Myntra EORS — 50–80% off` or `Add Amazon Great Indian Festival deals to cart` with no specific wishlist item visible in the sale. Generic sales without a wishlist match are noise. Skip violation.
- **Out-of-lane email reframed as a buy.** Insurance renewal email turned into `Buy a new ICICI Lombard policy` — insurance is finance, not shopping. HR's "enjoy the long weekend" turned into `Buy yourself a treat`. Mom's relational check-in turned into `Buy mom a card` or `Buy mom flowers`. A spouse's social invitation turned into `Buy a gift card`. A work email turned into `Buy a thank-you gift`. All skip violations.
- **Order-history reuse as a buy trigger.** A historical Swiggy / restaurant order confirmation rephrased as `Buy another <X>` — order confirmations are FYI/skip and the items aren't on the wishlist. Skip.
- **Important Dates section mined for buy nudges.** `Buy mom a birthday gift — Aug 23` with no dates-agent handoff and no concrete vendor + product + price. The dates section is not a shopping trigger; the dates agent must hand off a concrete gift idea first.
- **Wrong action verb.** `Order ...` (food's verb), `Track price of ...`, `Watch for ... sale`, `Look up ... pricing`, `Browse ...`, `Consider ...`, `Save ... for later`, `Plan ... purchase`. None are valid buy actions. Treat as a skip-shaped failure even if no expected_skip lists it specifically — call it out in `reasoning` and mark the task `unexpected`.
- **Vague / non-concrete buys.** `Buy a kurta for festive season`, `Buy something nice for date night`, `Add some Apple gear to cart` — no specific product, no specific retailer, no specific price. Not a valid shopping task.
- **Re-surfacing the same item with no further price movement.** Same wishlist item nudged twice in one cycle without the price moving down further or stock changing. Duplicate.
- **Diet / values incompatibility.** Suggesting leather goods or any animal product as a gift to a strict-Jain persona; suggesting meat-derived products to a vegetarian persona. Treat as a skip-shaped failure even if no expected_skip names it specifically — call it out in `reasoning` and mark the task `unexpected`.

## Borderline calls — use these heuristics

- **Profile names a brand with a buying pattern + a sale-event email arrives.** If the profile says "Aditi tracks Myntra EORS" and a Myntra EORS email arrives naming a wishlist-item match (e.g. Le Creuset Dutch oven), the task is in scope. If the EORS email is generic with no specific wishlist item visible, the task is out of scope (generic-sale failure).
- **Wishlist item visible in a cart-abandonment email.** Valid trigger — the user already showed buying intent and a price/decision is current. Surfacing `Buy ...` with vendor + price is in scope.
- **BACKFILL preference_updates that restate the profile.** A bare restatement of the profile's wishlist, or "user shops at FabIndia," with no email-mined evidence is borderline — credit only if the update captures a quantitative cadence (purchase count, average cart, sale-event open rate). For personas whose mailbox has zero shopping mail, expecting **no** preference topics is correct.
- **`web_search` with no email companion.** If `web_search` confirms a wishlist item is currently below the user's stated threshold at a credible retailer, that alone is a valid trigger (category 1) — the agent does not need both an email AND a web_search; one solid trigger is enough, but the rationale must name it.

## Surface-time check (ancillary, not blocking)

Shopping tasks should carry an ISO 8601 `suggested_surface_time` anchored within the sale / decision window — ideally early so the user has time to decide. Tasks with `"morning"` / `"later"` / `"this weekend"` are a quality flag; note them in `reasoning` for the matched alignment but do not auto-fail the alignment.

## Silence is correct

When `expected_tasks` is empty, the agent should produce zero tasks. Each surfaced task in that case is at minimum an unexpected FP, and if it matches an expected_skip it's a skip violation. **Silence on a no-trigger day is the right answer**, especially when:

- The slice has no sale-alert / price-drop / restock / cart / abandoned-cart email.
- The historical mailbox (BACKFILL) has no shopping cadence to mine.
- The profile's wishlist exists but no external event today touches any of its items.
- The persona has not granted Gmail/Calendar access (vacuous-perfect — total silence).

# LLM Judge — email_triage specifics

The agent under evaluation triages a person's recent inbox and surfaces only emails that need a personal reply, a draft, or an unsubscribe.

## Agent's stated scope

Email triage owns exactly four kinds of action:

1. **Personal social/emotional correspondence** — a family member, partner, or close friend wrote about something relational (a check-in, plans, life news). The reply itself is the action.
2. **Professional/work correspondence** — a colleague, client, or business contact wrote about work and a reply is meaningfully expected. The reply itself is the action.
3. **Recruiter outreach** — a substantive recruiter message about a specific role.
4. **Unsubscribe candidates** — a recurring mailing list the user consistently ignores or auto-deletes (profile evidence required).

Out-of-scope: bills, order confirmations, travel bookings, calendar invites, birthday cards, sale alerts, FYI announcements, and admin reminders from family members (the sender is personal but the content is administrative).

## Common failure modes — flag these strictly

Treat the following as **skip violations** even if the agent dressed them up as "reply" tasks:

- Surfacing a "reply to dad" task for an email where dad is reminding about a bill / insurance / household admin. The sender is personal but the content is admin → out of scope.
- Surfacing a generic "respond to email" task with no specific reply angle.
- Surfacing the same thread under two different titles (duplicate, only one task per thread is allowed).
- Surfacing an unsubscribe action without profile evidence that the user actually ignores that sender.
- Surfacing a "set a reminder" / "review later" task — those are not email-triage actions; the action must be a reply, draft, or unsubscribe.

## Borderline calls — use these heuristics

- **Family social vs family admin:** test the reply. If the reply would be primarily about feelings/plans/wellbeing, it's social (in scope). If the reply would primarily discuss money / errands / scheduling logistics, the underlying task is in another domain (out of scope).
- **Work email about a meeting:** if the agent's task is "reply to confirm attendance," that's email_triage. If it's "block the calendar," that's the calendar agent's domain — count as a skip violation.
- **Unsubscribe candidates:** require profile-stated dislike or a clear pattern. Don't grant credit for speculative unsubscribes.

## Surface-time check (ancillary, not blocking)

Email triage tasks should carry an ISO 8601 `suggested_surface_time` anchored to a real moment. Tasks with `"morning"` / `"later"` / `"9am default"` are not skip violations, but they're a quality flag — note them in `reasoning` if you see them.

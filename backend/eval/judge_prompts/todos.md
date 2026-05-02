# LLM Judge — todos specifics

The agent under evaluation tracks self-made commitments the user has put in writing (outbound emails or meeting-recap action items the user owns) and surfaces nudges as deadlines approach.

## Agent's stated scope

To-dos & commitments owns exactly three kinds of action:

1. **Self-made deliverable commitments** — the user wrote, in an outbound message, "I'll send X by Y" / "I'll have it ready by Z" / "Let me get back to you on this by Friday". The action is delivering on that promise.
2. **Action items from meeting recaps** — a recap email or calendar-event description explicitly assigns the user a deliverable with a date.
3. **Overdue self-commitment check-ins** — a previously-made user commitment is past its deadline by >3 days with no delivery evidence; surface a gentle follow-up.

The action verb must start with `Send`, `Deliver`, or `Follow up with`. The task source must cite either an outbound email FROM the user or a recap explicitly naming the user as action-item owner.

Out-of-scope: bills (finance), insurance/subscription renewals (finance), inbound personal/work emails awaiting reply (email_triage), inbound invitations/requests with no committed reply yet (email_triage), travel check-ins (travel), gift purchases (dates / shopping), calendar prep nudges (calendar), food orders (food), and any "todo" manufactured from profile narrative without an email/calendar trigger.

## Common failure modes — flag these strictly

Treat the following as **skip violations** even if the agent dressed them up as `Send / Deliver / Follow up` tasks:

- Surfacing a "Follow up with dad on insurance renewal" task — the source is a forwarded admin reminder from a family sender, not a user-made commitment. Belongs to finance/email_triage.
- Surfacing a "Follow up with mom on her check-in" task — replying to a relational message is email_triage, not a tracked deliverable commitment.
- Surfacing a "Follow up with Sudipto on bridge" or "Follow up with Mitali on breakfast" task on Arjun — both are **inbound** invitations; the user has not committed to anything.
- Surfacing a "Deliver audit review to Nilesh" task on Devendra — Nilesh's email is inbound and contains no Devendra-made commitment.
- Surfacing a "Send price list to art collector" task on Arjun — the price-list-request emails are inbound asks; no outbound Arjun commitment exists in the mailbox.
- Surfacing any task whose rationale boils down to "the profile says the user tends to drop X" with no specific email/calendar source. Profile patterns are not deadlines.
- Surfacing bills, travel bookings, food orders, or hotel reservations as "deliverables" or "follow-ups". They belong to finance / travel / food.
- Surfacing a task with a generic verb (`Reply`, `Pay`, `Renew`, `Confirm`, `Check`, `Schedule`, `Set a reminder`, `Wish`, `Buy`) — the action shape is wrong, regardless of underlying intent.

## Borderline calls — use these heuristics

- **Inbound vs outbound source:** the only valid commitment source is something the **user** wrote. If the cited message is FROM the user, it can ground a commitment task; if the message is TO the user, it cannot — even if it phrases things as a request with a date.
- **Recap action items:** a meeting-recap or calendar-event description is a valid source ONLY if it names the user as action-item owner with a specific deliverable + date. Generic agendas ("discuss pricing") do not assign ownership.
- **Overdue check-ins:** require evidence in the user's outbound history that a commitment was made AND no later evidence of delivery. Don't grant credit for speculative "they probably owe X" follow-ups.
- **BACKFILL personas:** if the historical mailbox contains zero outbound user emails with commitment language, both `tasks` and `preference_updates` should be empty. The agent should not echo profile narrative back as preference updates — BACKFILL job is to mine email evidence.
- **Profile-stated drop-tendencies:** ("user always files reimbursements late", "tracks school fee deadlines") are personality patterns, not commitments. They inform tone but cannot ground a task without an email/calendar trigger.

## Surface-time check (ancillary, not blocking)

Tasks should carry an ISO 8601 `suggested_surface_time` anchored to a real moment, generally 24h before the deadline (or on the deadline morning if no time was given). Tasks with `"morning"` / `"later"` / `"today sometime"` are quality flags — note in `reasoning`, but they are not skip violations on their own.

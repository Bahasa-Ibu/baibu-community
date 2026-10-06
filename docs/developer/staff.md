# Staff review

Staff (users with *staff status*) have a work area at `/staff/`, linked
from the navigation. It has four screens.

| Screen | Path | What it shows |
| --- | --- | --- |
| Overview | `/staff/` | Counts: submissions to review, reported replies, submissions with an issue, failed replies and tool calls in the last 7 days. |
| Submissions | `/staff/review/submissions/` | Submissions in `needs_review` or `issue`, oldest first, filterable by status. |
| Reported replies | `/staff/review/chats/` | Open reports of assistant replies, oldest first. |
| Errors | `/staff/errors/` | Submissions with an issue and their reason, failed chat replies (error code, model, attempt) and failed tool calls from the last 7 days. |

## One decision per item

Each item gets exactly one decision. Decisions lock the row and check its
state, so if two reviewers open the same item, the second one to save is
told it was already decided and nothing changes. After saving, the next
item in the queue opens.

**Submissions.** The page shows the cleaned text and the text as
submitted side by side, with the cleaning outcome (cleaner, quality score,
toxicity, redactions, detected language, reason) and the consent tier.
Decisions:

- *Accept* (`verified`) or *Reject* (`rejected`): records the reviewer and
  time and sends the contributor a [notification](notifications.md).
- *Clean again*: sends the submission back to `pending` and through the
  cleaning pipeline.

Only the decisions allowed from the current status are offered (see the
status table in [Submissions and cleaning](submissions.md)). Staff notes
are never shown to the contributor.

**Reported replies.** Users can report any assistant reply in their own
conversations (*Report* under the reply), choosing a reason and adding an
optional note. Each user can report a reply once. Staff see the whole
conversation with the reported reply highlighted, and decide *Problem
confirmed* or *No problem*. The reporter is notified that the report was
reviewed; the decision and staff notes are not shown to them.

Reviewing a report means reading that user's conversation. Say so in your
privacy notice.

## Access

Staff status is enough for these screens. The Django admin remains
available for detailed records; links from the errors page to admin records
appear only for users allowed to view them.

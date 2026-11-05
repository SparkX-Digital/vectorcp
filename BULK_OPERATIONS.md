# Selected account and website changes

These tools are part of the Unreleased 0.4.3 development source. They are not
included in the immutable 0.4.2 download.

## Accounts

Owners and resellers can select up to 100 permitted accounts to lock or enable
panel access, or assign a hosting plan. The agent validates the complete
selection and uses one database transaction. A refused account or incompatible
plan rolls back the account batch. Owner locks and reseller scope still apply.
Locked accounts continue to reserve their hosting allowance. Account access
changes do not suspend websites.

## Websites

In **Websites & domains**, select up to 20 websites and choose **Change selected
websites…**. Review the named domains, select suspension or activation, and apply.
Filtering clears selections hidden by the new filter. Customers do not receive
these administration controls.

The browser submits the existing individually authorized website operation in
selection order. Each request verifies the current session, role, ownership,
owner hold, active hosting jobs and request verification token in the agent.
Suspension returns HTTP 503 for ordinary website requests; it does not lock the
customer's panel access or stop its application services. Existing certificate
challenge handling stays available. An owner suspension creates an owner hold;
only the owner can release it.

The result dialog reports every selected domain:

- **Activated / Suspended:** the server confirmed the change.
- **Refused:** the server rejected this domain, for example because of an owner
  hold or running hosting operation. Other permitted domains can still complete.
- **Result unconfirmed:** a response was lost or the server failed. The browser
  stops the remaining changes and does not retry. Refresh that domain's status
  before deciding whether another request is needed.
- **Not attempted:** a preceding uncertain response or expired session stopped
  the batch before this domain was submitted.

Website batches are not an all-or-nothing transaction. Completed changes stay
applied. Keep the page open until the result dialog appears; closing/reloading
the page cannot reverse requests already sent. The interface prevents closing
the dialog during requests and asks before leaving the page, where the browser
supports that prompt. It does not claim durable background continuation.

See [VERIFICATION.md](VERIFICATION.md) for browser, unit, native endpoint evidence
and the distinction between the tested native baseline and this UI follow-up.

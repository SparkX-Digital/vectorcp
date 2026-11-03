# VectorCP interface contract

The server owner and reseller manage customers, packages and operations. A
customer manages its own websites and tools. Both use the same components and
spacing scale; navigation is scoped to the signed-in role. This document covers
the implemented interface, not a claim of complete backend functionality.

## Layout and size scale

| Element | Desktop | Phone, at or below 760 CSS pixels |
| --- | --- | --- |
| Navigation | 240 px, independently scrollable | Modal drawer, at most 300 px and always leaves 48 px of backdrop |
| Main toolbar | At least 64 px high | Wrapping toolbar with a full-width tool search |
| Page gutter | 24 px | 16 px |
| Page heading | 28 px | 26 px |
| Body text | 14 px | 14 px; form inputs 16 px |
| Helper and table-header text | At least 12 px | At least 12 px |
| Buttons and fields | At least 40 px high | At least 44 px high |
| Tool groups | Two columns; three above 1600 px | One column |
| Information column | 260 px; 300 px above 1600 px | Follows the tools |
| Panels and dialogs | 4–6 px corner radius | Same scale |
| Dialog | At most 560 px, with 16 px viewport clearance | Scrolls vertically within viewport |

Spacing uses 4, 8, 12, 16, 20 and 24 px. Colours, primary controls and shared
dimensions are declared in `vectorcp/static/style.css`. Fonts use the operating
system stack; there are no external font requests. Original brand assets stay
in their natural aspect ratio.

## Interaction rules

- The Tools page groups working entry points by purpose. Search matches names,
  descriptions and synonyms. Empty results explain how to recover; clearing
  search restores the directory. Every listed tool opens an implemented screen
  or form. Availability still depends on account permissions and server setup.
- Planned systems belong in the capability catalog and release status. Do not
  add controls that simulate successful mail, DNS, security or billing work.
- Group headings are buttons with `aria-expanded` and `aria-controls`.
- Mobile navigation traps keyboard focus, closes with Escape, makes background
  content inert and returns focus to its trigger when dismissed. Selecting a
  page closes the drawer and focuses that page's heading.
- Forms use visible labels. Dialogs have accessible titles/descriptions, focus
  the first field, retain native Escape behavior and show validation errors.
- Tables retain column relationships. A narrow viewport scrolls the table
  region, not the document; regions have labels and keyboard focus. Long
  domains, tokens, paths and error messages wrap without widening the page.
- All interactive controls have a visible focus indicator. Information is
  expressed in text as well as colour. Reduced-motion preferences are honored.
- Background job polling is limited to operation/status pages, so it cannot
  rebuild a file editor while the operator is typing.

## Review before shipping interface changes

Check owner, reseller and customer navigation; populated and empty pages;
permission failures; search and no-results; group collapse; every form and
dialog; long domains/filenames; table scrolling; keyboard focus and Escape.
Check at 320, 390, 463, 768, 1280 and 1920 CSS pixels. Distinguish responsive
markup checks from actual browser/API workflows when recording evidence.

Do not certify every display or browser from a single screenshot. Functional
service acceptance, installation and recovery remain separate requirements in
[CAPABILITIES.md](CAPABILITIES.md) and [VERIFICATION.md](VERIFICATION.md).

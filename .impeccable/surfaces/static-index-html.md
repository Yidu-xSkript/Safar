---
version: 1
slug: "static-index-html"
primary_target: "static/index.html"
related_targets: []
---

# Surface: Safar trip desk (static/index.html)

Mode: Operate. Single app screen: brief composer, proposal output, agent coupon trace.
Audience/job: travel-agency agent turns a client brief into a priced, checkable proposal; evaluators open the hosted link cold.
Constraints: demo inventory must be labelled; SSE/state logic in index.html and app.py stays intact; React via esm.sh + htm, no build.
Memorable moment: each lookup is issued as a numbered coupon (CPN 01…) and the proposal cites those numbers.
Unresolved: hosting target.

## Direction contract

THESIS: The quote is an issued ticket and every lookup a numbered coupon the agent tore off to build it. Refuses the category default of a chat column with grey collapsible "tool step" chips.

OWN-WORLD: Coupon-stock mint (#dcebe1) ticket panels on a cool off-white ground (#f7f8f4), navy ink (#1c2a44) for type, rules and the header, carbon red (#b3352b) only for live/issuing state, errors and the primary action. Archivo for the voice; Martian Mono only for data (flight codes, times, fares, coupon numbers). Dashed perforations with notches split ticket from stub. Drawn SVG pictograms, 1.5px stroke.

STORY: The agent pastes a brief, watches coupons issue on the right as the agent searches, then reads a proposal whose prices cite CPN numbers they can open and check, and refines it in follow-ups.

FIRST VIEWPORT: 60px navy-ruled header: Safar, "Agency trip desk", demo-inventory label, New trip. Left work area (fluid): the empty ticket explains the mechanism in one line and offers three client briefs; once running, the client brief sits right-aligned in navy, then the proposal ticket (Markdown body + perforated stub with route, dates, coupon count and model usage). Composer pinned at the bottom (textarea + red Send/Stop). Right rail, 420px, pale mint: "Coupons" heading and the coupon stack. Mobile: the rail becomes a horizontal coupon strip above the composer.

FORM: Flight Coupon, IMPECCABLE'S PICK (rank 1 on the grounded list), seed key 10c0d26d. Signature move: coupon issuance (navy number block, red while issuing; the result summary stamps in on completion).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

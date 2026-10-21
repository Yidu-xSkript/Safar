---
name: Safar
description: Agency trip desk. The quote is an issued ticket; every lookup is a numbered coupon.
colors:
  ground: "#f7f8f4"
  stock: "#dcebe1"
  rail: "#eaf1ea"
  paper: "#ffffff"
  ink: "#1c2a44"
  ink-2: "#44526b"
  rule: "#a9c3b2"
  carbon: "#b3352b"
  carbon-deep: "#962a21"
typography:
  display:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(28px, 3.2vw, 38px)"
    fontWeight: 800
    lineHeight: 1.08
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 800
    lineHeight: 1.2
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  data:
    fontFamily: "Martian Mono, ui-monospace, monospace"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.3
    fontFeature: "tnum"
  label:
    fontFamily: "Martian Mono, ui-monospace, monospace"
    fontSize: "12px"
    fontWeight: 400
    letterSpacing: "0.02em"
    fontFeature: "tnum"
rounded:
  none: "0px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "14px"
  lg: "18px"
  xl: "22px"
  gutter: "44px"
components:
  button-primary:
    backgroundColor: "{colors.carbon}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0 26px"
  button-primary-hover:
    backgroundColor: "{colors.carbon-deep}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "7px 14px"
  button-ghost-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
  input-composer:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "11px 14px"
  ticket:
    backgroundColor: "{colors.stock}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "22px 26px 24px"
  coupon:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "10px 12px"
  coupon-number:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.stock}"
    typography: "{typography.data}"
    width: "64px"
  coupon-number-live:
    backgroundColor: "{colors.carbon}"
  client-brief:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
---

# Design System: Safar

## Overview

**Creative North Star: "The Flight Coupon"**

Safar's quote is an issued airline ticket, and every lookup the agent makes is a numbered coupon torn off to build it. The system borrows the materials of paper travel documents: mint coupon stock on a cool off-white counter, navy ink for type and rules, dashed perforations with punched notches, and monospaced data printed like a fare box. It refuses the chat-column default of grey collapsible "tool step" chips; the agent's work is a stack of issued documents, not a transcript.

Density is operational. The work area holds the client brief, the proposal ticket, and the composer; a 420px pale-mint rail holds the coupon stack. Everything is square-cornered and ruled, depth comes from stock colour and ink rules rather than shadows, and one carbon red is reserved for things that are live, failed, or the primary action.

**Key Characteristics:**
- Square-cut paper documents: zero radius everywhere; the only curves are the punched notches.
- Navy ink rules (2px structural, 1.5px object outlines, 1px quiet dividers in the rule green).
- Dashed perforations separate ticket from stub and coupon number from coupon body.
- Archivo speaks; Martian Mono prints data (codes, dates, fares, coupon numbers), uppercased like a ticket.
- Carbon red marks only live/issuing state, errors, and the primary action.

## Colors

A cool, low-chroma travel-document palette: mint stock and navy ink, with a single carbon red.

### Primary
- **Carbon Red** (carbon): the issuing colour. Primary action (Send/Stop), the coupon number block while a lookup is running, ISSUING and VOID status text, error borders, the focus ring, the text caret, and the blinking pending square.
- **Deep Carbon** (carbon-deep): hover state of the primary action only.

### Neutral
- **Navy Ink** (ink): all primary text, the 2px header and composer rules, object outlines, the ticket perforation, the coupon number block at rest, and the client brief's fill.
- **Faded Ink** (ink-2): secondary text, stub labels, table headers, ledes, disabled outlines.
- **Coupon Stock** (stock): the ticket (proposal and empty-state) panel, and the number text on navy coupon blocks.
- **Rail Mint** (rail): the coupon rail's background.
- **Counter White** (ground): page ground, header and composer bands; also the notch punch-out colour.
- **Paper** (paper): coupon bodies, the composer field, text on navy.
- **Rule Green** (rule): 1px dividers, table row rules, dashed placeholder outlines, scrollbars.

### Named Rules
**The Carbon Copy Rule.** Red means something is happening, went wrong, or is the one action to take. A finished coupon, a settled proposal, and any decoration stay navy and mint.

**The Ink Inversion Rule.** Selection and the client's own words invert to navy with paper or stock text; the agent's output always sits on stock or paper.

## Typography

**Display Font:** Archivo (with system-ui)
**Data Font:** Martian Mono (with ui-monospace)

**Character:** A sturdy grotesque at heavy weight for the voice, paired with a wide mono that prints data the way a ticket printer does. Mono is never used for prose.

### Hierarchy
- **Display** (800, clamp(28px, 3.2vw, 38px), 1.08, -0.025em): the empty-state headline on the intro ticket.
- **Headline** (800, 26px, 1.15, -0.02em): proposal section headings; the stub's fare total runs at 30px in the same voice.
- **Title** (800, 18px, 1.2): rail heading ("Coupons").
- **Body** (400, 15px, 1.55): proposal prose and briefs, capped at 72ch inside the ticket; 13px for rail ledes and notes.
- **Data** (Martian Mono 600, 15px, 1.3, tabular): stub values, coupon numbers.
- **Label** (Martian Mono 400 to 600, 11 to 13px, tabular, uppercase): stub labels, coupon tool names, routes, status lines, table headers (11px, 0.06em tracking), the demo-inventory tag.

### Named Rules
**The Printer Rule.** Anything a ticket printer would print (flight codes, dates as 12NOV, times as 0930, fares, CPN numbers, status) is Martian Mono with tabular figures. Sentences are Archivo.

## Layout

A full-height app grid: 60px header over a two-column main area. The left column (fluid) stacks brief, proposal tickets and the pinned composer, each capped at 920px and centred, with 28px/44px padding and 18px between items. The right column is a fixed 420px coupon rail, scrolling independently, divided from the work area by a 2px navy rule. Tickets split into a fluid main panel and a 210px stub.

Spacing runs on a loose 4px-derived ladder (6, 10, 14, 18, 22, 28, 44px): 10px between coupons and composer parts, 14px inside the stub, 22px ticket and rail padding, 44px work-area gutter.

Below 900px the rail becomes a horizontal coupon strip (250px coupons, 220px notes) between the log and the composer; the ticket stub drops below the main panel with a horizontal perforation; gutters shrink to 16px; rail headings, request heads and coupon result tables are hidden.

## Elevation & Depth

Flat. There are no shadows. Depth is tonal and ruled: counter-white ground, mint stock for tickets, paper for coupons, navy for the inverted client brief, and ink rules to separate bands. The only inset outline is the disabled primary button's 1.5px faded-ink ring.

### Named Rules
**The Paper Stack Rule.** Surfaces separate by stock colour and ink rule, never by shadow or blur.

## Shapes

Every surface is square-cut (0 radius). The one curve is the punched notch: 20px circles in the ground colour at both ends of a ticket perforation, cut into the stock. Perforations are 2px dashed (navy on stock tickets, stock on the navy coupon number block); dashed rule-green outlines mark empty placeholders and proposal section breaks. Icons are drawn SVG line pictograms at 16px, round caps and joins, stroked in currentColor.

## Components

### Buttons
- **Shape:** square (0 radius).
- **Primary:** carbon fill, paper text, Archivo 600, 0 26px padding, full composer height. Hover deepens to carbon-deep. Disabled drops to transparent with faded-ink text and a 1.5px inset faded-ink ring. While running it becomes Stop, same treatment.
- **Ghost:** 1.5px navy border, transparent, 600 14px, 7px 14px. Hover inverts to navy fill with ground text; disabled at 45% opacity.
- **Focus:** every focusable element takes a 2px carbon outline at 2px offset.

### Inputs / Fields
- **Composer:** paper field with a 1.5px navy border, square, 11px 14px padding, inheriting body type; sits in a ground band under a 2px navy rule. The caret is carbon.

### Ticket (signature)
Mint stock panel split by a 2px dashed navy perforation into a main panel (proposal Markdown or the intro) and a 210px mono stub with label/value pairs, an optional fare-box total (Archivo 800 30px plus a mono alternate currency), and an issued line that reads red while issuing or failed. Ground-coloured notches punch both ends of the perforation. Errors print a VOID stamp: carbon text in a 1.5px carbon box.

### Coupon (signature)
A paper card with a 1.5px navy outline, laid out as a 64px number block and a body. The number block is navy with stock "CPN" and a two-digit number, separated from the body by a 2px dashed stock perforation. While issuing the block and outline turn carbon and the status reads ISSUING…; on completion the result summary stamps in (scale 1.08 to 1, 0.3s). Errors invert the block to paper with carbon text and outline. Each coupon issues with a left-to-right clip reveal (0.42s, cubic-bezier(.16, 1, .3, 1)). Results open in a details row as a compact mono fares table.

### Client Brief
Right-aligned navy block, paper text, max min(560px, 85%), 12px 16px padding. The client's words are the only inverted text block in the log.

### Lists and Tables
Proposal tables: mono 11px uppercase headers over a 2px navy rule, 1px rule-green row dividers, right-aligned final column, bold final row as the total. The empty-state brief list uses the same ruling (2px navy top, 1px rule rows); hover underlines in carbon.

## Do's and Don'ts

### Do:
- **Do** keep every surface square-cut and separate it with stock colour and ink rules.
- **Do** print codes, dates, times, fares and coupon numbers in Martian Mono with tabular figures, uppercase where a ticket would.
- **Do** split a document from its stub with a 2px dashed perforation and punch ground-coloured notches at its ends.
- **Do** reserve carbon for live/issuing state, errors, focus and the single primary action.
- **Do** label demo inventory wherever prices appear.
- **Do** draw icons as 16px stroked SVG pictograms in currentColor.

### Don't:
- **Don't** add shadows, blur or rounded corners; the notch is the only curve.
- **Don't** use carbon red for decoration, completed states, or secondary actions.
- **Don't** set prose in Martian Mono or data in Archivo.
- **Don't** render agent steps as grey collapsible chat chips; they are numbered coupons.


## Dark theme

The same ticket read under night light. It follows the system setting unless the viewer picks one with the header's
sun/moon toggle (stored as `safar.theme`, shared by the trip desk and landing page). Printed client quotes are always light.

| Token | Light | Dark |
|---|---|---|
| ground | #f7f8f4 | #10151d |
| stock (ticket) | #dcebe1 | #1b2a28 |
| rail | #eaf1ea | #141b22 |
| paper (coupons, cards) | #ffffff | #18202a |
| ink | #1c2a44 | #e3e9e4 |
| ink-2 | #44526b | #a3b0bd |
| rule | #a9c3b2 | #3a4d47 |
| carbon (text, borders) | #b3352b | #ff7a62 |
| carbon-fill (buttons, live coupons; white text) | #b3352b | #b3352b |

Carbon splits in two because one red can't do both jobs on a dark ground: text needs to be brighter to stay readable,
and a filled button needs to stay deep for its white label. Inverted elements (client brief, coupon number blocks) keep
their roles: ink-coloured block, paper-coloured text. The landing page's "Under the hood" band stays dark in both themes.

## Model settings dialog

Native `<dialog>` opened with `showModal()`: Escape and backdrop click close it, focus starts on the provider field.
Paper card with a 1.5px ink border on a `--backdrop` scrim, 22px rise-in (respects reduced motion).

<!-- Open, non-binding notes from the finish review (not yet built): notches on rail coupons at the number-block perforation; a stronger validation stamp on completed coupons. -->

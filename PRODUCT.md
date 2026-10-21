# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated. Python FastAPI backend (`app.py`) runs a Claude tool-use agent loop and streams events over SSE. The frontend is React 19 loaded from esm.sh with htm, in one `static/index.html` with no build step, so the app runs with a single `uvicorn` command. React matches the target job's stack (React or Vue).

## Users

Primary: a travel-agency agent (a staffer at a travel company) who plans and quotes trips for clients. A client brief comes in ("5 days in Istanbul, 2 adults, about $1,500") and the agent needs priced flight and hotel options, a total, and alternatives fast enough to reply to the client.

Evaluating audience: the hiring team for an AI Developer role at MMCY / Mod Eth Outsource PLC (Addis Ababa), a company that builds engineering teams for travel-industry businesses. They will open a hosted link on their own, with no one walking them through it, so the product has to explain itself.

## Product Purpose

Safar is an agent copilot for travel agencies. It turns a plain-language client brief into a priced, client-ready trip proposal by searching flights and hotels, converting currency and comparing options. Every step the agent takes is visible as it happens. Success means the agent gets a quote they could send, and the evaluator understands within a minute how the AI system works and that it was built with production discipline.

## Positioning

Transparency is the differentiator. The agent's reasoning and every tool call (inputs, status and results) stream live beside the answer, so the user can check the work before quoting it to a client. It is an inspectable copilot, not a black-box chatbot.

## Operating Context

- Agent workflow: client brief, then agent search (flights, hotels, FX), then a proposal with a cost table and alternatives, then follow-up refinements in the same session.
- Home market is East Africa: Addis Ababa Bole (ADD) is the hub, and ETB appears next to USD.
- Opened on desktop by evaluators from a hosted URL; must work on mobile too.

## Capabilities and Constraints

- Tools: `search_flights` (one-way, one date), `search_hotels` (city, check-in, nights, optional nightly cap), `convert_currency` (fixed set: USD, ETB, EUR, GBP, AED, KES, TRY).
- All inventory and FX rates are deterministic **demo data**: the same query returns the same results. The UI must never imply live prices or real bookings.
- No booking, payment or user accounts. Sessions live in server memory.
- Model: Claude (`claude-opus-5`) with adaptive thinking (summarized reasoning is streamed) and server-side refusal fallbacks.
- Open: hosting target, and abuse/cost protection for a public link.

## Brand Commitments

Name: **Safar** (Amharic/Arabic/Persian for "journey"). Neutral product: no personal branding in the app. Author credit lives in the README only.

## Evidence on Hand

None. There are no real customers, testimonials, metrics or partner airlines. Airline names appear only as demo inventory; never present them as partners or live fares.

## Product Principles

1. Show the work: every claim in a proposal traces back to a visible tool result.
2. Proposal-ready output: answers are structured for forwarding to a client, not chatty.
3. Honest about data: demo inventory is labelled as demo.
4. Self-explanatory: a first-time evaluator understands what to try and what they are seeing without a guide.

# Case selection: matched pairs (Step 3)

Feasibility study only (PRD §17), not validation. Five verified pairs. Records are in `data/cases/*.json` and are validated by `deal_radar.cases`.

Companies House data comes from the official API (read-only GET of the company profile and the PSC list). Web pages were opened in this session on 27 Oct 2026.

## Pairs

| Pair | Deal company (CH no.) | Control (CH no.) | Owner type | Sector | Anchor date | Buyer | Why this control matches | Deal source |
|---|---|---|---|---|---|---|---|---|
| P1 | HSL Compliance Group Ltd (11738872) | Premier Technical Services Group Ltd, "PTSG" (06005074) | PE-backed | UK building compliance / TICC | 2025-02-04 | IK Partners (IK Small Cap III), from LDC | Both are PE-owned UK compliance-services consolidators (fire, water, electrical testing). PTSG has been PE-owned since 2019 (Macquarie), with Warburg Pincus joining in 2021. PTSG is about 2x larger by headcount (~1,400 vs ~650). | [IK release](https://ikpartners.com/press-release/ik-partners-to-invest-in-hsl-compliance/), [LDC release](https://www.ldc.co.uk/news/ldc-exits-hsl-compliance/) |
| P2 | Peak AI Ltd (09307701) | Causaly Ltd (11368328) | VC-backed | UK AI software | 2025-03-12 | UiPath | Both are UK AI software scale-ups with similar funding (Peak: USD 75m Series C, SoftBank VF2, 2021; Causaly: USD 93m total, ICONIQ-led Series B, 2023). Both have diffuse VC ownership with no registrable PSC. | [Peak repost of UiPath release](https://peak.ai/hub/blog/uipath-acquires-peak-to-launch-vertically-specialized-agents-within-its-agentic-automation-platform/) |
| P3 | Oxford Ionics Ltd (11795789) | Universal Quantum Ltd (11710367) | VC-backed | UK quantum hardware (trapped-ion on chips) | 2025-06-09 | IonQ | Both are university spin-outs with the same technology approach (microwave-controlled trapped ions on silicon chips). Both are VC-backed, with founders as registered PSCs. | [IonQ release](https://ionq.com/news/ionq-announces-agreement-to-acquire-oxford-ionics-accelerating-path-to-pioneering) |
| P4 | Cytora Ltd (08229538) | Artificial Labs Ltd (08766928) | VC-backed | UK insurtech (commercial/specialty insurance workflow software) | 2025-09-09 | Applied Systems | Both are London-market insurtech software for commercial insurers, VC-backed with diffuse ownership (no registrable PSC). | [Cytora release](https://cytora.com/risk-flow-center/blog/cytora-acquired-by-applied-systems-accelerating-the-shared-vision-of-delivering-the-digital-roundtrip-of-insurance) |
| P5 | Signal Media Ltd, "Signal AI" (08468207) | Cognism Ltd (09392705) | VC-backed | UK B2B data/intelligence SaaS | 2025-09-24 | Battery Ventures (majority) | Both are London B2B data-intelligence SaaS companies with similar funding scale (Cognism USD 87.5m Series C, 2022), diffuse VC ownership and no registrable PSC. | [Signal AI release (PR Newswire)](https://www.prnewswire.com/news-releases/signal-ai-announces-165-million-investment-round-led-by-battery-ventures-to-redefine-risk-and-reputation-intelligence-302565334.html) |

### Deal cross-checks (Companies House PSC)
| Deal | PSC change seen | Note |
|---|---|---|
| HSL | Mariner Bidco notified 2025-03-28; LDC (Managers) ceased the same day | Completion after announcement; consistent. |
| Peak | UiPath UK Ltd notified **2025-03-07** | The PSC date is **before** the announcement (deal completed, then announced with UiPath results). Point-in-time check: only the 12 Mar announcement is used as the event date. |
| Oxford Ionics | IonQ, Inc. notified 2025-09-16 | Completion; consistent. |
| Cytora | Applied individuals 2025-09-10, Applied UK Holdings II 2026-01-12 | Consistent. |
| Signal AI | Kalahari Bidco notified 2025-10-28 | Consistent. |

## Control verification (anchor −12 months to anchor +12 months)

Every control was checked against all four label sources. Method:
1. **Press releases:** web search on the company name + acquired/acquisition/investment/sale/funding, plus a dated news search.
2. **RNS:** web search restricted to investegate.co.uk and londonstockexchange.com on the company name. This method is shown to work: it returns real DCC disposal RNS items.
3. **CMA:** gov.uk CMA case search (`gov.uk/cma-cases?keywords=<name>`).
4. **Companies House PSC:** official API, used as a cross-check only.

| Control | Search terms | Press releases | RNS | CMA | PSC (cross-check) |
|---|---|---|---|---|---|
| PTSG | "PTSG Premier Technical Services Group sale OR acquired OR new owner 2024 2025 2026"; "PTSG building compliance news 2025 2026 Warburg Pincus sale OR exit" | Nothing after the 2021 Warburg/Macquarie deal | Only the 2019 Macquarie takeover RNS (outside the period) | "PTSG": 0. "Premier Technical Services": no case names PTSG | PTSG's immediate PSC is Graphmars Bidco (since 2022), unchanged. Note: at Graphmars Holdco one "control as firm" individual was replaced by another on 2024-09-02. This is not evidence of a deal, and no other source shows one. |
| Causaly | "Causaly acquired OR acquisition"; "Causaly biomedical AI company news 2025 2026 funding acquisition" | Latest event is the 2023 Series B | No mentions | 0 | No registrable PSC since 2018, unchanged |
| Universal Quantum | "Universal Quantum acquired OR acquisition OR merger"; "Universal Quantum Brighton news 2025 2026 funding OR acquired OR merger" | May 2026 report that US SPACs **approached** the company. Nothing was announced or agreed. | Only a 2022 minority investment by a listed holder (outside the period) | 0 | Founders 25–50% each since 2018, unchanged |
| Artificial Labs | "Artificial Labs insurtech acquired OR acquisition OR investment 2025 2026" | USD 45m Series B on 2026-02-03 (CommerzVentures lead). Minority growth equity, out of scope (PRD §4). | Mentioned in a listed investor's annual report (minority) | 0 | No registrable PSC since 2019, unchanged (consistent with no >25% holder) |
| Cognism | "Cognism acquired OR acquisition OR majority stake OR funding 2024 2025 2026"; "Cognism sales intelligence London news 2025 2026" | Founder/CEO replaced; reported investor dispute (Mar 2026). No transaction. | No mentions (results were Cambridge Cognition only) | 0 | No registrable PSC since 2020, unchanged |

## Rejected candidates

**Deals**
- Aquavista Watersides (Antin, 24 Sep 2025): no same-owner-type UK marina peer. MDL Marinas is owned by Yattendon Group, Premier Marinas by the Wellcome Trust, and Boatfolk was itself acquired in 2025.
- Medik8 (L'Oréal, 9 Jun 2025): no PE-backed UK skincare peer of similar size found. Liz Earle is a corporate subsidiary (Alliance Boots); NEOM is founder-held with a PE minority.
- Lyst (ZOZO, 9 Apr 2025): the only VC-backed UK fashion-marketplace peer found (Wolf & Badger) is far smaller.
- AAB (Goldman Sachs Alternatives, 1 Jul 2025): Companies House entity unclear (LLP and dormant holding companies; operating/holding chain not resolved).
- DCC Healthcare (Investindustrial, 22 Apr 2025): multi-entity division with no single UK entity identified; EV GBP 1.05bn is at the top of mid-market.
- Exertis UK & Ireland (AURELIUS, Jul 2025): multi-entity carve-out, ~GBP 2bn revenue; the main UK entity is now in administration.
- Zip World (Dolphin Capital, Jan 2025): the primary sources give only "January 2025", with no exact announcement date.
- Iglu (Flight Centre): announced 10 Dec 2025, outside the window.
- Outside the window: Sedex (2026), Wifinity (2026), Global Autocare (2026), WCCTV (2026), My Pension Expert (2026), NRG Riverside (2024), Acal BFi (2021), Wood UK T&D (Dec 2025).
- TitanHQ: Irish, not UK.
- CSL (ECI continuation fund): unclear whether this is a change of control, and its date is inconsistent across ECI pages.

**Controls**
- Mind Foundry and Oxford Quantum Circuits: PSC changes inside the check period. Not investigated further; a cleaner peer was used instead.
- Concirrus: PSC change at its holding company in Oct 2024, inside Cytora's check period.
- Obsequio Group: much smaller than HSL; PTSG preferred.
- Tractable: much larger than Peak.
- hyperexponential: not chosen; Artificial Labs' diffuse ownership is closer to Cytora's.
- Wolf & Badger: size mismatch with Lyst (see above).

## Caveats
- "Verified" means **no transaction found** in these four searches, not proof that none occurred. Web search indexes are incomplete, and private deals can go undisclosed (PRD §16).
- RNS coverage here relies on search-engine indexing of investegate.co.uk and londonstockexchange.com, not a direct full-text RNS query.
- PSC is a cross-check only. It shows only >25% holders, and deals often happen at holding-company level (Medik8's PSC did not change for the L'Oréal deal).
- The owner-type mix is skewed: 1 PE-backed pair and 4 VC-backed pairs. No carve-out pair could be matched in the time available, so H2 (PE and carve-outs most predictable) is barely tested.
- Size matching is approximate. Most companies disclose no revenue; funding scale and headcount were used as proxies. PTSG is about 2x HSL.
- The Oxford Ionics deal (USD 1.075bn) sits above a typical mid-market size, although the company is an early-revenue deep-tech business.
- Some "deal sources" are the target's own release or a repost of the acquirer's (Peak, Cytora, Signal AI). They are recorded under the `pe_or_acquirer_press_release` source type.
- Two controls had notable events inside their check period that are not changes of control: Artificial Labs (minority Series B) and Universal Quantum (reported SPAC approaches). Step 5 should record these as signals and counter-signals.

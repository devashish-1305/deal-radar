# Case selection: matched pairs (Step 3)

Feasibility study only (PRD §17), not validation. Six verified pairs (P1–P5 from the first pass, P6 added after gate feedback). Records are in `data/cases/*.json` and are validated by `deal_radar.cases`.

Companies House data comes from the official API (read-only GET of the company profile and the PSC list). Web pages were opened in this session on 27 Oct 2026.

## Pairs

| Pair | Deal company (CH no.) | Control (CH no.) | Owner type | Sector | Anchor date | Buyer | Why this control matches | Deal source |
|---|---|---|---|---|---|---|---|---|
| P1 | HSL Compliance Group Ltd (11738872) | Premier Technical Services Group Ltd, "PTSG" (06005074) | PE-backed | UK building compliance / TICC | 2025-02-04 | IK Partners (IK Small Cap III), from LDC | Both are PE-owned UK compliance-services consolidators (fire, water, electrical testing). PTSG has been PE-owned since 2019 (Macquarie), with Warburg Pincus joining in 2021. PTSG is about 2x larger by headcount (~1,400 vs ~650). | [IK release](https://ikpartners.com/press-release/ik-partners-to-invest-in-hsl-compliance/), [LDC release](https://www.ldc.co.uk/news/ldc-exits-hsl-compliance/) |
| P2 | Peak AI Ltd (09307701) | Causaly Ltd (11368328) | VC-backed | UK AI software | 2025-03-12 | UiPath | Both are UK AI software scale-ups with similar funding (Peak: USD 75m Series C, SoftBank VF2, 2021; Causaly: USD 93m total, ICONIQ-led Series B, 2023). Both have diffuse VC ownership with no registrable PSC. | [Peak repost of UiPath release](https://peak.ai/hub/blog/uipath-acquires-peak-to-launch-vertically-specialized-agents-within-its-agentic-automation-platform/) |
| P3 ⚠ size outlier | Oxford Ionics Ltd (11795789) | Universal Quantum Ltd (11710367) | VC-backed | UK quantum hardware (trapped-ion on chips) | 2025-06-09 | IonQ | Both are university spin-outs with the same technology approach (microwave-controlled trapped ions on silicon chips). Both are VC-backed, with founders as registered PSCs. **Size outlier:** the USD 1.075bn deal value is above mid-market. Kept for now (gate decision). | [IonQ release](https://ionq.com/news/ionq-announces-agreement-to-acquire-oxford-ionics-accelerating-path-to-pioneering) |
| P4 | Cytora Ltd (08229538) | Artificial Labs Ltd (08766928) | VC-backed | UK insurtech (commercial/specialty insurance workflow software) | 2025-09-09 | Applied Systems | Both are London-market insurtech software for commercial insurers, VC-backed with diffuse ownership (no registrable PSC). | [Cytora release](https://cytora.com/risk-flow-center/blog/cytora-acquired-by-applied-systems-accelerating-the-shared-vision-of-delivering-the-digital-roundtrip-of-insurance) |
| P5 | Signal Media Ltd, "Signal AI" (08468207) | Cognism Ltd (09392705) | VC-backed | UK B2B data/intelligence SaaS | 2025-09-24 | Battery Ventures (majority) | Both are London B2B data-intelligence SaaS companies with similar funding scale (Cognism USD 87.5m Series C, 2022), diffuse VC ownership and no registrable PSC. | [Signal AI release (PR Newswire)](https://www.prnewswire.com/news-releases/signal-ai-announces-165-million-investment-round-led-by-battery-ventures-to-redefine-risk-and-reputation-intelligence-302565334.html) |

| P6 | AAB, via group topco Pioneer Topco Ltd (13638179) | Xeinadin, via group topco Xeinadin Topco 1 Ltd (13833419) | PE-backed | UK accountancy / professional services | 2025-07-01 | Goldman Sachs Alternatives, from August Equity | Both are PE-backed UK accountancy consolidators of similar scale (AAB ~GBP 100m revenue and 1,000+ staff; Xeinadin ~GBP 155m revenue in 2024). This is a same-sector match; the broad-sector relaxation was not needed. | [GS Alternatives release](https://am.gs.com/en-gb/advisors/news/press-release/2025/AAB) |

AAB's entity was resolved by following its PSC chain: AAB Business & Tax Advisory LLP (SO301668) → Pioneer Bidco Ltd (13639975) → Pioneer Topco Ltd (13638179). Pioneer Topco's PSC is August Equity's GP entity until it ceased; Seeker Bidco Ltd follows.

### Deal cross-checks (Companies House PSC)
"Notified" is when control began, as stated in the filing. "Filed" is the date the filing became public on Companies House. Only the filed date matters for point-in-time use.

| Deal | PSC change seen (notified → filed) | Note |
|---|---|---|
| HSL | Mariner Bidco notified 2025-03-28; LDC (Managers) ceased the same day | Completion after announcement; consistent. |
| Peak | UiPath UK Ltd: notified **2025-03-07**, filed **2025-03-18** (PSC02; PSC statement withdrawn the same day) | Control began before the announcement, but it only became public on 2025-03-18, **after** the 2025-03-12 announcement. No earlier public report found: TechCrunch (13 Mar 2025) says the deal was disclosed with UiPath's quarterly results and mentions no prior reports, and a search for pre-announcement talk or rumours found none. The anchor stays at 2025-03-12. |
| AAB | Seeker Bidco Ltd: first filed 2026-02-25 with notified date 2026-01-21; second filing 2026-03-31; August Equity GP cessation re-filed 2026-05-23 with date 2025-11-19 | Messy, corrected filings, all well after the 2025-07-01 announcement. A good example of why PSC is a cross-check only. |
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
| PTSG | "PTSG Premier Technical Services Group sale OR acquired OR new owner 2024 2025 2026"; "PTSG building compliance news 2025 2026 Warburg Pincus sale OR exit" | Nothing after the 2021 Warburg/Macquarie deal | Only the 2019 Macquarie takeover RNS (outside the period) | "PTSG": 0. "Premier Technical Services": no case names PTSG | PTSG's immediate PSC is Graphmars Bidco (since 2022), unchanged. The Graphmars Holdco change on 2024-09-02 is Warburg Pincus's internal CEO succession, not a deal; see "PTSG finding" below. |
| Causaly | "Causaly acquired OR acquisition"; "Causaly biomedical AI company news 2025 2026 funding acquisition" | Latest event is the 2023 Series B | No mentions | 0 | No registrable PSC since 2018, unchanged |
| Universal Quantum | "Universal Quantum acquired OR acquisition OR merger"; "Universal Quantum Brighton news 2025 2026 funding OR acquired OR merger" | May 2026 report that US SPACs **approached** the company. Nothing was announced or agreed. | Only a 2022 minority investment by a listed holder (outside the period) | 0 | Founders 25–50% each since 2018, unchanged |
| Artificial Labs | "Artificial Labs insurtech acquired OR acquisition OR investment 2025 2026" | USD 45m Series B on 2026-02-03 (CommerzVentures lead). Minority growth equity, out of scope (PRD §4). | Mentioned in a listed investor's annual report (minority) | 0 | No registrable PSC since 2019, unchanged (consistent with no >25% holder) |
| Cognism | "Cognism acquired OR acquisition OR majority stake OR funding 2024 2025 2026"; "Cognism sales intelligence London news 2025 2026" | Founder/CEO replaced; reported investor dispute (Mar 2026). No transaction. | No mentions (results were Cambridge Cognition only) | 0 | No registrable PSC since 2020, unchanged |
| Xeinadin | "Xeinadin accountancy group Exponent owner revenue 2025 sale OR acquired OR new investor"; "Xeinadin acquired OR agreed to sell OR majority stake 2025 2026 accountancy" | Exponent ran a sale process in 2025 (reported ~GBP 800m target, May 2025), but it was **shelved with no bids** ([PE Wire, 2 Feb 2026](https://www.privateequitywire.co.uk/exponent-abandons-1bn-sale-of-uk-accountancy-group-xeinadin/)). Exponent remains the owner. No transaction was announced; only Xeinadin's own bolt-on acquisitions. | Only an unrelated credit-union report naming Xeinadin Audit as auditor | 0 | Topco 1 PSCs (Xeinadin Member GP, Xeinadin Debtco 1) unchanged since 2022 |

### PTSG finding (P1 control): kept verified
- **What changed:** at Graphmars Holdco Ltd (13232295), two levels above PTSG, Charles Robert Kaye (PSC since 2021-02-27, address "C/O Warburg Pincus LLC, 450 Lexington Avenue, New York") ceased on 2024-09-02. Jeffery David Perlman (nature: "significant influence or control **as firm**") was notified the same day. Both filings (PSC07, PSC01) were made public on 2025-02-27.
- **Public explanation:** [Bloomberg Law, 17 Jul 2024](https://news.bloomberglaw.com/esg/warburg-pincus-names-jeffrey-perlman-ceo-succeeding-chip-kaye): Warburg Pincus named Jeffrey Perlman CEO, succeeding Chip Kaye, effective 2 Sept. [Wikipedia](https://en.wikipedia.org/wiki/Warburg_Pincus) gives Kaye's name as "Charles R. 'Chip' Kaye". The PSC date matches the succession date exactly, and the controlling firm (Warburg Pincus) is unchanged.
- **Ties to a sale?** None found in press, RNS or CMA. PTSG's own PSC (Graphmars Bidco) is unchanged.
- **Conclusion:** this was an internal leadership change at the existing owner, not a change of control of PTSG. P1 stays **verified**.

## Rejected candidates

**Deals**
- Aquavista Watersides (Antin, 24 Sep 2025): no same-owner-type UK marina peer. MDL Marinas is owned by Yattendon Group, Premier Marinas by the Wellcome Trust, and Boatfolk was itself acquired in 2025.
- Medik8 (L'Oréal, 9 Jun 2025): no PE-backed UK skincare peer of similar size found. Liz Earle is a corporate subsidiary (Alliance Boots); NEOM is founder-held with a PE minority.
- Lyst (ZOZO, 9 Apr 2025): the only VC-backed UK fashion-marketplace peer found (Wolf & Badger) is far smaller.
- (AAB was rejected in the first pass because its entity was unclear. It was resolved after gate feedback and is now P6.)
- Fieldway (Foresight → Axis CLC): announced 2026, outside the window.
- J&J Global Fulfilment (LDC → QLS): announced Nov 2025, outside the window.
- Focus Group (Bowmark → Hg): Hg backing reported by 2024; no 2025 announcement found.
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
- Dains (AAB control candidate): IK Partners took a majority stake in Dec 2024, inside AAB's check period. Dains Accountants Ltd's own PSC (Brewer Bidco since 2021) did **not** change, so PSC alone would have missed this deal.
- Sumer (AAB control candidate): ~3x AAB's size, and its owner is weighing a sale or continuation fund. Avoided.

## Caveats
- "Verified" means **no transaction found** in these four searches, not proof that none occurred. Web search indexes are incomplete, and private deals can go undisclosed (PRD §16).
- RNS coverage here relies on search-engine indexing of investegate.co.uk and londonstockexchange.com, not a direct full-text RNS query.
- PSC is a cross-check only. It shows only >25% holders, and deals often happen at holding-company level (Medik8's PSC did not change for the L'Oréal deal).
- The owner-type mix is skewed: 2 PE-backed pairs (P1, P6) and 4 VC-backed pairs. The gate asked for 2–3 new PE pairs; only 1 was found within the ~45-minute time box. No carve-out pair could be matched, so H2 (PE and carve-outs most predictable) is barely tested.
- Size matching is approximate. Most companies disclose no revenue; funding scale and headcount were used as proxies. PTSG is about 2x HSL.
- The Oxford Ionics deal (USD 1.075bn) sits above a typical mid-market size, although the company is an early-revenue deep-tech business.
- Some "deal sources" are the target's own release or a repost of the acquirer's (Peak, Cytora, Signal AI). They are recorded under the `pe_or_acquirer_press_release` source type.
- Two controls had notable events inside their check period that are not changes of control: Artificial Labs (minority Series B) and Universal Quantum (reported SPAC approaches). Step 5 should record these as signals and counter-signals.

## Notes for later steps
- **Step 7:** a PSC or ownership change that **is** the deal itself (Mariner Bidco at HSL, UiPath UK at Peak, IonQ at Oxford Ionics, Applied at Cytora, Kalahari Bidco at Signal AI, Seeker Bidco at AAB) is the outcome, never a predictive signal. Exclude it from features even if its filing date falls before a snapshot date.
- **Point-in-time for PSC:** use the filing date only, never `notified_on`. Example: Peak's UiPath PSC was notified 2025-03-07 but filed 2025-03-18.
- **Post-anchor events at controls do not affect pre-anchor snapshots.** All snapshots fall before the anchor date, so these events can never enter features:
  - Artificial Labs Series B (2026-02-03, after its 2025-09-09 anchor);
  - Universal Quantum SPAC approach report (2026-05-26, after its 2025-06-09 anchor);
  - Xeinadin sale shelved (2026-02).
- **In-window pre-anchor events at controls are real evidence.** Example: Xeinadin's reported 2025 sale preparation (May 2025, before the 2025-07-01 anchor) is an "exploring options" intent signal at a control that did **not** transact. It is a useful false-positive test case for steps 7–8.
- **PTSG outcome:** kept verified. The only PSC change in the period (Graphmars Holdco, 2024-09-02) is Warburg Pincus's CEO succession (Kaye → Perlman), with no change of owner. See "PTSG finding" above.

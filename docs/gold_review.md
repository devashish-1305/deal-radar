# Gold labels for review (Step 6, Phase A)

The gold labels are in `data/cases/gold_signals.json`. They were written by an AI model (Claude) **before** any extraction prompt, extractor code or LLM output existed. No `data/raw/llm/` cache exists, and a test enforces that. They are for your review before Phase B.

## Scope
- **In scope:** Evidence records usable at the pair's anchor (publication_date not None and < anchor) that also pass the content-leak check.
  - **16 articles**, holding **18 gold signals**.
  - **4 articles** have no signals.
- **Content-leak exclusion (new in 6a):** a deterministic check runs in `scripts/collect_evidence.py`, using `evidence.content_leak`.
  - **Rule:** a page is excluded as `content_leak` if its stored text contains either:
    - the pair's buyer name, from `data/cases/leak_check.json` (used only for this check, never in queries); or
    - a target-outcome phrase such as "<target> acquired by" or "acquisition of <target>".
  - **Why exclude, not clean:** once a page carries post-anchor content, we cannot know what else changed. Excluded pages are not cleaned up, and the stored raw text is not modified.
  - **Which items:** 8 opened candidates were flagged, listed in `docs/evidence_log.md` under "Excluded as content_leak". 6 of them had previously been kept, so `evidence.json` went from 43 to 37 records. Only one of the 6 was in scope, because the other five were undated:

| evidence_id | published | hit | note |
|---|---|---|---|
| ev-oxford_ionics-f7f92b5f3c | 2023-09-01 | "IonQ" | Quantum Insider article on the £2m NSSIF round. The page carries the tag "Oxford Ionics [Acquired by IonQ]" and a link titled "IonQ Completes Acquisition of Oxford Ionics" (Sept 2025). **This was in scope; it is now excluded.** |
| ev-hsl_compliance-99d9835669 | None | "IK Partners" | was undated, so it was already unusable |
| ev-hsl_compliance-b54ca9408a | None | "IK Partners" | was undated, so it was already unusable |
| ev-signal_ai-637c921455 | None | "Battery Ventures" | was undated, so it was already unusable |
| ev-aab-e5685ef297 | None | "Goldman Sachs" | was undated, so it was already unusable |
| ev-aab-94c6254fe3 | None | "Goldman Sachs" | was undated, so it was already unusable |

The other two flagged candidates (`ev-signal_ai-c2a4fa9d83` and `ev-oxford_ionics-51c13d874a`) are syndicated or locale copies. Before this change they had been discarded as duplicates; the leak check now logs them as leaks instead.

## Labelling rules
1. **Target company only.** Sector-context sentences are not labelled, so `external_context` types (peer deals, active buyers, sector consolidation) get no gold labels. They are listed below under "Excluded sector-context sentences".
2. **A sponsor's investment in the target** is labelled `pe_holding_period` only. It is not also labelled `recently_acquired`, because Step 7 derives that from the same date. Later restatements of the start date ("Since securing investment from August Equity in October 2021") are labelled too, because they date the clock.
3. **`large_recent_fundraise`:** PRD §8 defines neither "large" nor "recent". Every disclosed equity round is labelled as a fact, whatever its size or age, with the amount and date in the quote or event date. **Step 7 applies the size and recency thresholds.**
4. **Acquisitions made by the target** are not a PRD §8 signal, so they are not labelled.
5. **Advisers on a completed past deal** do not count as `advisers_appointed`, which means a mandate for a prospective transaction.
6. **Status:**
   - `confirmed`: stated by the company or a party to the deal.
   - `attributed`: a report that cites a named source.
   - `speculative`: unsourced conjecture.
7. **Quotes** are the shortest verbatim span from the article body, at most 25 words, never taken from sidebars or page chrome. Every quote is tested as a substring of the stored text.

## Gold signals, one row per article

| evidence_id | company | title | published | gold signals (type · status · quote) | reason |
|---|---|---|---|---|---|
| ev-ptsg-2276fbd570 | ptsg | Macquarie completes acquisition of the UK's Premier Technical Services Group for more than £300 Million | 2019-07-31 | pe_holding_period · confirmed · "has today announced the successful completion of its latest private equity investment, the acquisition of the UK's Premier Technical Services Group (PTSG)" | Macquarie's take-private completes, which starts the PE holding clock. |
| ev-ptsg-a027db6cd8 | ptsg | Warburg Pincus invests alongside Macquarie Capital Principal Finance … | 2021-05-17 | (1) pe_holding_period · confirmed · "it has entered an agreement with Macquarie Capital Principal Finance ("Macquarie Capital") to jointly acquire a majority stake in Premier Technical Services Group Ltd"<br>(2) pe_holding_period · confirmed · "Macquarie Capital acquired a majority stake in PTSG in 2019 in a take-private transaction." | (1) A new sponsor, Warburg Pincus, takes a joint majority stake. (2) A restatement of Macquarie's 2019 entry. |
| ev-peak_ai-a644f27c4f | peak_ai | Peak AI raises $75m to fund AI-based corporate decision support platform | 2021-09-02 | (1) large_recent_fundraise · confirmed · "British startup Peak AI has closed a $75 million Series C funding round, led by SoftBank Vision Fund 2."<br>(2) large_recent_fundraise · confirmed · "Peak's Series B, which closed in February, raised the firm $21m, with Oxx leading that round." | Two disclosed equity rounds. |
| ev-oxford_ionics-543ab30517 | oxford_ionics | Oxford Ionics raises £30m with participation from Prosus Ventures | 2023-01-09 | large_recent_fundraise · confirmed · "Oxford Ionics raises £30m with participation from Prosus Ventures" | A £30m Series A. |
| ev-artificial_labs-bc9a862bce | artificial_labs | Artificial Labs raises £8M Series A+ round to drive growth | 2024-02-07 | (1) large_recent_fundraise · confirmed · "Artificial Labs, a leading algorithmic underwriting InsurTech, has successfully concluded an £8M Series A+ funding round"<br>(2) new_cfo_or_chair · confirmed · "the appointments of Ascot founder Martin Reith as Chairman in 2022" | (1) A disclosed round. (2) A new chair, appointed in 2022. |
| ev-signal_ai-fc9d3d7854 | signal_ai | Signal AI acquires risk data firm Social 360 | 2024-02-16 | large_recent_fundraise · confirmed · "Signal AI, which raised $50m in 2021" | A past round mentioned in passing (2021). Step 7 decides on recency. The acquisition itself is not labelled (rule 4). |
| ev-aab-f2a91fefa7 | aab | AAB secures significant investment from August Equity | 2021-10-26 | pe_holding_period · confirmed · "Anderson Anderson & Brown (AAB) has secured a significant investment from August Equity" | August Equity's investment starts the PE holding clock. |
| ev-aab-8a6861f66c | aab | AAB hires new CEO as it targets £100m revenue | 2023-11-07 | (1) governance_change · confirmed · "AAB announced the appointment of Emma Lancaster as its new chief executive."<br>(2) pe_holding_period · confirmed · "Since securing investment from August Equity in October 2021, AAB Group has completed nine acquisitions" | (1) CEO succession. The outgoing CEO moves to a group executive director role focused on M&A. (2) A restatement of the sponsor's entry date. |
| ev-aab-f5ed4daff0 | aab | Accountancy firm Ormsby & Rhodes to merge with UK-based AAB | 2025-01-22 | pe_holding_period · confirmed · "Since securing investment from August Equity in 2021, AAB has trebled in size" | A restatement of the sponsor's entry. The merger is made by the target (rule 4). |
| ev-xeinadin-27a448b196 | xeinadin | Xeinadin appoints new CFO for UK and Ireland | 2024-03-18 | new_cfo_or_chair · confirmed · "Xeinadin appoints new CFO for UK and Ireland" | A new CFO, Chantelle Grobler, whose experience includes M&A. |
| ev-xeinadin-c34d355840 | xeinadin | Professional services group Xeinadin agrees private equity partnership and investment | 2022-02-10 | (1) pe_holding_period · confirmed · "Exponent, which has a track record in the professional services sector, will make a significant minority investment in Xeinadin"<br>(2) governance_change · confirmed · "Mark Taylor and Tom Lightowler of Exponent will join Xeinadin's Board" | (1) The sponsor's entry. **This was a significant MINORITY investment with board seats, not a majority buyout** (borderline, see below). (2) Sponsor partners join the board. |
| ev-xeinadin-1678c55951 | xeinadin | Xeinadin reportedly gearing up for £800m private equity sale | 2025-05-26 (late) | (1) exploring_options · attributed · "Xeinadin is preparing for a sale exceeding £800m (approximately $1.1bn) to private equity investors, The Times has reported."<br>(2) advisers_appointed · attributed · "has engaged Evercore's investment banking advisers to initiate the auction process." | A reported sale process with a named bank, sourced to The Times, so the status is attributed. This is the logged Step 5.1 exception. |

In the table, curly quotes are shown as straight quotes. The JSON keeps the exact characters from the source.

## Articles with no signals

| evidence_id | company | title | published | why no signal |
|---|---|---|---|---|
| ev-cytora-65c38c74db | cytora | Cytora announces expanded advisory board with former senior executive from PartnerRe joining | 2024-03-19 | An *advisory* board is not the company board, so this is not a governance_change (borderline, see below). |
| ev-signal_ai-85c934c567 | signal_ai | UK-based Signal AI fortifies … with Social 360 acquisition | 2024-02-16 | The target is the acquirer (rule 4). This copy does not mention the 2021 raise. |
| ev-cognism-5244a86892 | cognism | Código promocional de Cognism … | 2023-12-27 | A Spanish coupon and marketing page with no company events. |
| ev-xeinadin-776e274fc5 | xeinadin | Xeinadin acquires Raffingers in largest deal to date | 2025-03-19 | The target is the acquirer (rule 4). The sector sentence is excluded (rule 1). |

## Excluded sector-context sentences (rule 1)
- **ev-aab-f5ed4daff0:**
  - "The small- to mid-tier Irish accounting sector has seen a surge in deal making in the past two years…" (sector consolidation).
  - Peer deals by ETL Global, Azets, Dains and Moore Ireland.
- **ev-xeinadin-776e274fc5:** "Xeinadin's acquisition aligns with a broader trend of consolidation in the UK accountancy sector".
- **ev-xeinadin-1678c55951:** "Evelyn Partners divested its Professional Services business to funds advised by British private equity firm Apax in November 2024" (a peer deal).

## Borderline or unresolved decisions (for your call)
1. **£2m NSSIF round (Oxford Ionics) as `large_recent_fundraise`.** It would have been labelled under rule 3, but its article (`ev-oxford_ionics-f7f92b5f3c`) is now excluded as `content_leak`. That article's NED appointment (Dipesh Patel, governance_change) is lost with it. Both remain listed here so the gap is visible. Rule 3 also labels small rounds, such as Artificial Labs' £8M, and old ones, such as Signal AI's 2021 $50m and Peak's Series B. Step 7 must apply the thresholds.
2. **Xeinadin and Exponent as `pe_holding_period`.** Exponent made a *significant minority* investment with board seats; it did not take control. The label is kept because Exponent is the sponsor and the clock is relevant, but it is not a majority holding-period start.
3. **Cytora's advisory board is not labelled `governance_change`.** An analyst who treats advisory-board expansion as pre-sale readiness would label it.
4. **AAB 2023, "AAB Group has never been a more attractive platform for investment" (August Equity partner),** is not labelled `exploring_options`, because it is not a stated sale intent. A looser analyst might call it speculative intent.
5. **Xeinadin 2022, "Xeinadin was advised by Canaccord Genuity, Hill Dickinson and EY",** is not labelled `advisers_appointed`. These are advisers on the completed Exponent deal (rule 5), so this is a deliberate trap for the extractor.
6. **AAB 2023 CEO change as `governance_change`.** PRD §8's readiness types name the CFO and chair specifically. A CEO succession is classed as governance_change, not new_cfo_or_chair.
7. **Two copies of the Signal AI / Social 360 story are both in scope** (different titles, so not deduplicated). Only the uktech.news copy mentions the 2021 $50m raise, so the gold labels differ between the two copies. This follows each article's own text.
8. **For Step 8, not a labelling issue:** Xeinadin is the **control** company in P6, yet it carries the strongest direct-intent signals in the set, a reported sale process with advisers appointed (2025-05-26). This is recorded here so the benchmark discussion can address it.

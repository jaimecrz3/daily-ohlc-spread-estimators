# Speaker notes

Use these as prompts, not a memorized script. Default ten-slide flow; appendix slides are Q&A material.

## Slide 1 — Title

Objective: Frame the economic question.

Say aloud: Daily price summaries are widely available, but execution-cost information is harder to obtain. This presentation asks which existing daily estimator best tracks a common intraday proxy.

Transition: Start with the question and the original expectations.

## Slide 2 — Research question

Objective: Establish falsifiable prior expectations.

Say aloud: We compare CS, AR and EDGE rather than build a new estimator. The original expectations favored EDGE, downward CS bias in thin markets, and stable class rankings. Those expectations were recorded before provider performance and remain open to contradiction.

Transition: Explain the sample on which the question can actually be answered.

## Slide 3 — Data and design

Objective: Show scope and conditioning without an inventory tour.

Say aloud: The completed comparison spans stocks, ETFs, futures and crypto, stratified independently by liquidity. The common-defined sample is smaller than the eligible design, and class calendars differ. FX remained in scope but blocked, with no substitute source.

Transition: Show how daily estimates and the intraday proxy enter the same comparison.

## Slide 4 — How the horse race works

Objective: Define the target and error criteria.

Say aloud: Each daily spread estimate is compared with the one-minute Roll measure on exactly the same asset-days. Bias describes the average signed gap, MAE typical absolute discrepancy, and RMSE gives large errors more weight. HAC inference concerns signed bias only; the accuracy ranking is descriptive.

Transition: Give the overall accuracy answer before discussing its boundaries.

## Slide 5 — EDGE performs best overall

Objective: Deliver the central overall finding.

Say aloud: EDGE roughly halves typical absolute error relative to CS and AR in the frozen sample. Its advantage is against Roll, not an observed true execution cost, and it remains positively biased overall. No statistical-superiority test was specified for MAE or RMSE differences.

Transition: Ask whether that ordering survives when markets are separated.

## Slide 6 — There is no universal estimator ranking

Objective: Make the class boundary unmistakable.

Say aloud: ETFs favor CS on both criteria, while stocks favor EDGE on MAE and CS on RMSE. Futures and crypto favor EDGE on both. The figure adds tier detail; its individual cells should not be confused with the class-aggregate matrix.

Transition: Translate those boundaries into evidence about the original hypotheses.

## Slide 7 — Hypotheses: what survived?

Objective: Retain adverse and partial findings.

Say aloud: Overall EDGE leadership is partial support for dominance, not universal confirmation. Its raw-negative-rate lead also has class exceptions, while positive LOW-tier CS bias contradicts the directional expectation. Stable rankings across classes are not supported.

Transition: Explain the benchmark limitation that conditions every accuracy claim.

## Slide 8 — Roll availability is the main sample bottleneck

Objective: Make sample selection central to credibility.

Say aloud: Roll availability is the main bottleneck, particularly for ETFs. Our accuracy comparison is conditional on all measures being defined, so it cannot rank methods on the unavailable days. The coverage thresholds shown on the right are sensitivity diagnostics, not the primary sample.

Transition: Check whether the overall finding depends on specific conventions.

## Slide 9 — The overall conclusion survives the major sensitivity checks

Objective: Separate robust overall results from fragile local results.

Say aloud: Overall EDGE leadership survives the applicable coverage, weighting and convention sensitivities. ETF and stock class leaders are preserved under matched adjusted and unadjusted Bloomberg comparisons. The stock abs-root and asset-omission results show why local conclusions need qualification.

Transition: Close with the answer and its economic scope; diagnostic material remains available in the appendix.

## Slide 10 — Conclusion

Objective: Answer the research question directly.

Say aloud: EDGE is the strongest overall match to the frozen Roll benchmark, but method choice depends on asset class and the error criterion. Daily OHLC spread estimators are useful, but they are not interchangeable across market structures.

Transition: Invite questions; use the optional appendices only for the topic raised.

Optional A1 prompt: the cross-fitted model predicts errors rather than generating new spreads; emphasize association, mechanical input overlap and the persistence shown by the lag placebo. If used instead of the main sensitivity slide, return directly to the unchanged conclusion.

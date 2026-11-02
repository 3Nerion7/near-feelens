# Cheap execution does not remove the balance tied to state

## A conditional long-term adoption thesis

For a NEAR application that creates persistent state, affordable consumed gas is only one part of an economically viable design. Under fixed protocol-price assumptions, the modeled storage balance grows with retained billable bytes. A bounded retention policy caps that modeled stock, while the consumed-gas value proxy continues to grow with operations. A credible long-term adoption case for such an application therefore needs an explicit state-retention and capital plan, alongside its execution assumptions.

This is a conditional application-economics thesis, not evidence that demand will grow, that all applications need deletion, or that the NEAR token will appreciate. Stateless applications and applications whose net billable state is already bounded are counterexamples to a universal retention claim. We do not recommend buying, selling or allocating money to any asset.

## What anchors the model

The frozen public mainnet sample contains 24 finalized ancestor headers and their pinned protocol configuration. It preserves 240 newly included chunk headers. The 23 adjacent header intervals span 13.276897340 seconds. The newest header reports a gas price of 100,000,000 yoctoNEAR/gas, and the pinned configuration reports a storage parameter of 10^19 yoctoNEAR/byte. These are real captured fields; keeping them constant in a future model is an assumption.

The aggregate reported gas_used / gas_limit ratio is 0.003908665199, approximately 0.39086652%. The reported previous-execution balance_burnt fields sum to 0.058450094041894 NEAR. Official nearcore representation maps those chunk fields to previous-execution values. Their executions must not all be assigned to the 13-second header timestamp span. These observations are not a long-term usage sample and are not extrapolated into future operations, annual revenue, issuance or adoption.

The protocol min_gas_price field is 1,000,000,000, different from the observed header price. We preserve both. Official gas documentation distinguishes purchase-price floors, consumed-gas pricing and refunds. The scenario uses its explicitly stated static header-price anchor; it is neither an upfront gas quote nor a complete transaction payment.

## Reproducible workload, not a forecast

Declare horizon H, daily operations O, consumed Tgas per operation G, net billable state bytes per operation B, and retention days R. Let P be the captured gas-price anchor and S the captured storage parameter. The optional gas stress multiplier M is either 1 or 10. All workload inputs are assumed, not benchmarked or inferred from the small sample.

```text
cumulative consumed-gas value proxy = H × O × G × 10^12 × P × M
modeled retained bytes               = min(H, R) × O × B
modeled balance with retention      = min(H, R) × O × B × S
modeled append-only balance         = H × O × B × S
```

Gas results are cumulative hypothetical flows. Storage results are balance stocks at the horizon. **Adding them into a total expense would be wrong.** B means additional net billable state after the user's assumed overhead and allowance treatment, not merely payload bytes. The retention model assumes real deletion or compaction can occur; this app does not implement or prove it. It excludes deletion gas, account-creation charges, account-specific allowance calculations, write-before-delete peaks, other storage overhead and future parameter changes.

Using 10,000 assumed operations/day, 5 Tgas/operation, 1,000 assumed net billable bytes/operation and 30-day retention:

| Horizon | Cumulative consumed-gas value proxy | Balance with retention | Append-only balance |
| --- | ---: | ---: | ---: |
| 30 days | 150 NEAR | 3,000 NEAR | 3,000 NEAR |
| 365 days | 1,825 NEAR | 3,000 NEAR | 36,500 NEAR |
| 1,095 days | 5,475 NEAR | 3,000 NEAR | 109,500 NEAR |

The retained state is 300,000,000 bytes in this idealized example; at 365 days the append-only comparison is 3,650,000,000 bytes. These are modeled stocks, not a deployed application's measured savings. A 10× gas-price stress multiplies only the gas proxy: the modeled storage balances stay unchanged. If retention is at least the horizon, its balance equals the append-only balance. If net state is zero, both storage balances are zero.

## What would support or weaken the thesis

The calculation supports one narrow design argument: retained state can dominate the modeled balance requirement even when the gas-value proxy is modest. It does not show how many users want the app or establish any token investment return. A real adoption study would need representative usage data, observed application-state growth, measured complete transaction charges, and evidence that users value the application enough to support its capital and operational requirements. That evidence is not fabricated here.

The principal countercase is an application with no growing billable state, an existing bounded-state design, or affordable capital that makes retention complexity unattractive. A further countercase is a workload where deletion/compaction is impossible or its costs and peak balances erase the modeled difference. The chart cannot settle these cases without application-specific experiments.

## Falsifiers and practical checks

1. An independent parser that cannot reproduce the exact pinned fields invalidates the observed anchors until corrected. Altered source bytes, duplicate new chunks and broken parent links stop the offline build.
2. A version-specific protocol implementation that differs materially from the stated previous-execution representation requires relabeling the observations. The linked current official source is not proof of the provider's exact running binary.
3. An application test that shows net billable state does not grow as O × B, or cannot be reduced to min(H, R) × O × B, falsifies this simple retention model for that application. Account allowances, overhead, write peaks and deletion costs must then be measured explicitly.
4. A future gas or storage parameter change invalidates the constant-price scenario; it does not become an observed loss or gain. The interface makes the gas stress assumption visible.
5. A representative longer sample may contradict the snapshot's low reported ratio. It would revise the network description, not change assumed future workloads into evidence.
6. Weak user demand or poor operational reliability would defeat an adoption thesis even if the arithmetic remains correct. Cheap execution alone is insufficient evidence of either adoption or token returns.

## Reproduce before judging

Run the offline build and tests, inspect the raw-byte manifest, then vary the horizon, workload, state and retention inputs. The Python and browser models use exact integer arithmetic for token amounts. Every result is reproducible without a wallet, cloud account, paid API, new dependency or transaction.

This is a local, AI-assisted research draft for independent review. It has not been submitted to a contest, won a prize, produced a customer sale or established investment performance. The human author must understand and review the final work before any publication.

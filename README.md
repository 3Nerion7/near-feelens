# NEAR FeeLens

A local, reproducible evidence app and conditional long-term thesis for state-growing NEAR applications: low consumed-gas value does not remove the balance tied to retained state. Inspect real price anchors, change declared workloads and compare storage-balance stocks without confusing them with cumulative spending. This is an unpublished programming-contest draft, not a submitted entry or a claimed award.

## Run it without accounts or installations

Requirements: existing Python 3.12+; a modern browser with BigInt support. The app uses the Python standard library and plain HTML/CSS/JavaScript. No pip, npm, cloud service, API key or wallet is needed.

```text
python -X utf8 feelens.py build
python -u -X utf8 feelens.py serve --port 8767
```

On Windows, `REGENERAR.cmd` rebuilds the evidence offline. `ABRIR-DEMO.cmd` builds and serves only the public demo files at `http://127.0.0.1:8767`. Open that address yourself. Ctrl+C stops the server. It is not scheduled or installed as a service.

## Try it: do X, see Y

1. Run `feelens.py build`. See a successful verification of all 24 frozen block responses and their pinned protocol response. The command makes **no network requests**.
2. Open the local demo. See 24 real finalized ancestor block headers, with a capture window of approximately 13.277 seconds. This is a header timestamp window, not the execution window of all fields carried in those headers.
3. Switch the chart between sample and full 0–100% scales. Values stay identical; the selected axis range is labeled explicitly.
4. Expand the table. Compare each point with its exact reported integers and hash-linked source evidence.
5. Leave the long-term defaults: 365 days, 10,000 assumed operations/day, 5 consumed Tgas/operation, 1,000 assumed net billable state bytes/operation and 30-day retention. See **1,825 NEAR** as the cumulative consumed-gas value proxy, **3,000 NEAR** as the modeled retention balance and **36,500 NEAR** as the append-only balance. These are assumptions applied to captured parameters, not observed spending, savings or a complete transaction quote.
6. Choose 10× gas-price sensitivity. The gas proxy increases tenfold; the storage balances stay unchanged. Set state bytes to zero and both storage balances become zero. Set retention longer than the horizon and its effective value is min(horizon, retention), matching append-only at that horizon.
7. Compare 30, 365 and 1,095 days. The chart contains only balance stocks; the table separately reports the cumulative gas proxy. No flow and stock are added into a total cost.
8. Enter 300.001 Tgas or an out-of-range operation count. The model refuses the input instead of displaying a plausible number.

## What the real snapshot contains

`data/manifest.json` records the endpoint, exact JSON-RPC methods and parameters, UTC capture timestamps, raw-byte SHA256 and file sizes. The newest block was requested with `finality: final`; the remaining 23 follow `prev_hash` exactly. Heights are 222762818 through 222762795. The pinned protocol configuration is requested at the newest block's hash.

The snapshot contains 24 block headers, 240 newly included chunk headers and a protocol configuration response. There were 28 public read-only RPC requests including three earlier feasibility checks. A separate private review corroboration added one request outside this snapshot. No transfers, signatures or account creation occurred. No collector runs when building or opening the app.

The verifier rejects changed bytes, wrong request/response identity, broken parent links, duplicate blocks or new chunks, duplicate shards, missing chunks, inconsistent masks, invalid integers and source files outside the expected raw-data paths. Raw nanosecond timestamps, yoctoNEAR and gas values never pass through JavaScript Number. Only bounded chart ratios use floating-point rendering; all scenario arithmetic uses BigInt in the browser and integer/Decimal arithmetic in Python.

## Metric meanings and boundaries

- **Header gas ratio:** sum of `gas_used` divided by sum of `gas_limit`, restricted to chunk headers whose `height_included` equals the containing block height. Previously carried headers are not counted again. The official nearcore source maps these `gas_used` values to **previous-execution** fields. This is a ratio of reported header fields, not a measurement of execution throughput in the 13-second capture window.
- **Reported `balance_burnt`:** an aggregate of the corresponding previous-execution header fields. It is not computed as gas × price, not called operating revenue and not used to infer whole-chain net issuance.
- **`total_supply`:** the exact reported block field. No annual issuance, inflation, price or investment-return calculation is inferred from this small sample.
- **Protocol version:** the protocol configuration's version at the pinned block is displayed separately from the set of `header.latest_protocol_version` values. Advertised header versions are not assumed to define the active version.
- **Scenario consumed-gas product:** operations × declared Tgas × the static observed header `gas_price`. This is not an upfront payment or guaranteed transaction total. Gas purchase-price floors, refunds, action charges and account-creation charges are outside this model.
- **Scenario storage balance:** additional bytes × the captured `storage_amount_per_byte`. It is gross arithmetic for additional state, not a recurring fee, unrecoverable expense or full account minimum. Account-specific allowances and fixed creation charges are excluded; releasing state can affect the balance requirement.
- **Long-term model:** horizon × assumed daily operations × consumed Tgas × static observed price produces a cumulative gas-value proxy. Storage uses min(horizon, retention) × assumed daily operations × net billable state bytes × captured storage parameter. Retention is independent from the horizon, both 1–3650 days. Net state must include the user's assumed overhead and allowance treatment. Deletion/compaction is hypothetical; deletion gas, write-before-delete peaks, feasibility and future parameter changes are excluded. It is not an extrapolation of the 13-second sample.

The captured header `gas_price` is 100,000,000 yoctoNEAR/gas, while the protocol `min_gas_price` field is 1,000,000,000. Both are preserved without treating the difference as corrupted data or enforcing equality. The gas documentation distinguishes purchase and consumed-gas prices. The scenario uses only its stated static observed price, not an invented mapping of every fee rule.

## Reproduce and test

```text
python -X utf8 -m unittest discover -s tests -v
```

Core tests need no network, packages or accounts. One cross-runtime parity test uses an existing Node.js if available and otherwise reports a skip; Node is not required to run the app. Tests use temporary copies and explicitly synthetic invalid mutations. The demo always uses the real frozen responses.

Two offline builds from identical source bytes must produce byte-identical `public/metrics.json` and `public/evidence.json`. Source failure stops the build; it does not silently substitute synthetic data. The server binds to `127.0.0.1` and serves an exact public-file allowlist, with directory browsing and source-data routes unavailable.

## Sources

- [NEAR Hackathon rules](https://nearhackathon.com/HACKATHON.md): AI code is allowed; prompts are examples, not mandatory paid services; local reproducible demos are allowed. No entry has been filed.
- [RPC providers](https://docs.near.org/api/rpc/providers): the selected FASTNEAR public endpoint is free; archival service is a different capability. No load test or automatic provider failover is performed.
- [Block and chunk RPC](https://docs.near.org/api/rpc/block-chunk) and [protocol configuration RPC](https://docs.near.org/api/rpc/protocol).
- [Pinned nearcore representation](https://github.com/near/nearcore/blob/818e6a28bbedf87ed2d145fd53150a4a5642e2b2/core/primitives/src/views.rs#L1187): `gas_used` and `balance_burnt` map to previous-execution fields. This verifies current official representation, not the exact binary run by the RPC provider.
- [Gas concepts](https://docs.near.org/protocol/transactions/gas) and [storage balance](https://docs.near.org/protocol/storage/storage-staking).

See `THESIS.md` for the conditional adoption argument, exact equations, 30/365/1095-day comparison, stateless countercase and falsification conditions. Cheap execution is not a prediction of adoption or token return. This project provides research tooling, not personalized investment advice. It uses Python's standard library and original plain JavaScript/CSS/HTML; development, tests and wording were assisted by OpenAI Codex agents. The human author must understand and review the final entry before any publication.

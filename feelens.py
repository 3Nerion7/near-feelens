"""NEAR FeeLens: reproducible public-data analysis, entirely offline by default."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import tempfile
import os
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
ENDPOINT = "https://free.rpc.fastnear.com"
YOCTO = 10**24
TGAS = 10**12
PUBLIC_FILES = {"index.html", "styles.css", "app.js", "scenario.js", "metrics.json", "evidence.json"}
HASH_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,64}\Z")


class DataError(ValueError):
    """Captured source data or a declared scenario is invalid."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def read_json(data: bytes):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(DataError("Non-finite JSON value")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DataError("Invalid UTF-8 JSON") from error


def integer(value, name, *, positive=False):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value):
        number = int(value)
    else:
        raise DataError(f"{name} must be an unsigned integer, never a float or boolean")
    if number < 0 or (positive and number == 0):
        raise DataError(f"{name} is outside its allowed range")
    return number


def decimal_text(value: Decimal | int) -> str:
    text = format(Decimal(value), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def token_text(yocto: int) -> str:
    # Manual integer formatting is exact regardless of Decimal's ambient precision.
    sign = "-" if yocto < 0 else ""
    whole, fraction = divmod(abs(yocto), YOCTO)
    return sign + str(whole) + (("." + str(fraction).zfill(24)).rstrip("0") if fraction else "")


def utc_ns(ns: int) -> str:
    seconds, fraction = divmod(ns, 10**9)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{fraction:09d}Z"


def scenario(operations, tgas_per_operation, storage_bytes, gas_price_yocto, storage_yocto_per_byte):
    ops = integer(operations, "operations")
    storage = integer(storage_bytes, "storage_bytes")
    price = integer(gas_price_yocto, "gas_price", positive=True)
    byte_cost = integer(storage_yocto_per_byte, "storage_amount_per_byte", positive=True)
    if ops > 1_000_000 or storage > 1_000_000_000:
        raise DataError("Scenario exceeds the declared input bounds")
    if not isinstance(tgas_per_operation, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,3})?", tgas_per_operation):
        raise DataError("Tgas must be a decimal string with at most three fractional digits")
    with localcontext() as ctx:
        ctx.prec = 100
        tgas = Decimal(tgas_per_operation)
        if not Decimal("0.001") <= tgas <= Decimal("300"):
            raise DataError("Tgas must be between 0.001 and 300")
        gas_units = int(tgas * TGAS) * ops
    execution = gas_units * price
    storage_amount = storage * byte_cost
    return {"kind": "hypothetical", "scope": "static observed price times assumed consumed gas; not a transaction quote",
            "operations": str(ops), "tgas_per_operation": tgas_per_operation,
            "storage_bytes": str(storage), "gas_units": str(gas_units),
            "gas_price_yocto_per_gas": str(price), "execution_cost_yocto": str(execution),
            "execution_cost_near": token_text(execution),
            "storage_balance_yocto": str(storage_amount), "storage_balance_near": token_text(storage_amount)}


def long_term_scenario(days, operations_per_day, tgas_per_operation, net_state_bytes_per_operation,
                       retention_days, gas_price_yocto, storage_yocto_per_byte, gas_price_multiplier="1"):
    horizon = integer(days, "horizon_days", positive=True)
    daily = integer(operations_per_day, "operations_per_day")
    state_bytes = integer(net_state_bytes_per_operation, "net_state_bytes_per_operation")
    retention = integer(retention_days, "retention_days", positive=True)
    price = integer(gas_price_yocto, "gas_price", positive=True)
    byte_cost = integer(storage_yocto_per_byte, "storage_amount_per_byte", positive=True)
    if horizon > 3650 or daily > 1_000_000 or state_bytes > 1_000_000 or retention > 3650:
        raise DataError("Long-term inputs exceed horizon/operation/state/retention bounds")
    if not isinstance(gas_price_multiplier, str) or gas_price_multiplier not in ("1", "10"):
        raise DataError("Gas-price sensitivity must be the explicit string 1 or 10")
    # Reuse the checked exact consumed-gas model for one assumed day. No time-series extrapolation.
    daily_model = scenario(daily, tgas_per_operation, 0, price * int(gas_price_multiplier), byte_cost)
    gas_units = int(daily_model["gas_units"]) * horizon
    gas_proxy = int(daily_model["execution_cost_yocto"]) * horizon
    retained_days = min(horizon, retention)
    retained_bytes = retained_days * daily * state_bytes
    append_bytes = horizon * daily * state_bytes
    retained_balance, append_balance = retained_bytes * byte_cost, append_bytes * byte_cost
    return {"kind": "hypothetical_long_term", "horizon_days": str(horizon),
            "operations_per_day": str(daily), "tgas_per_operation": tgas_per_operation,
            "net_state_bytes_per_operation": str(state_bytes), "retention_days": str(retention),
            "retained_days": str(retained_days), "gas_price_multiplier": gas_price_multiplier,
            "static_header_gas_price_yocto_per_gas": str(price), "model_gas_price_yocto_per_gas": str(price * int(gas_price_multiplier)),
            "storage_yocto_per_byte": str(byte_cost), "cumulative_consumed_gas_units": str(gas_units),
            "gas_billing_proxy_yocto": str(gas_proxy), "gas_billing_proxy_near": token_text(gas_proxy),
            "retained_state_bytes": str(retained_bytes), "append_only_state_bytes": str(append_bytes),
            "locked_storage_balance_yocto": str(retained_balance), "locked_storage_balance_near": token_text(retained_balance),
            "append_only_storage_balance_yocto": str(append_balance), "append_only_storage_balance_near": token_text(append_balance),
            "balance_difference_yocto": str(append_balance - retained_balance), "balance_difference_near": token_text(append_balance - retained_balance),
            "assumptions": ["Declared future workload, not predicted adoption or extrapolation of the header sample.",
                            "Prices stay static at the snapshot anchor, with an optional explicit gas-price sensitivity multiplier.",
                            "Net billable state bytes per operation include assumed overhead/allowance treatment; this is not payload size.",
                            "Retention assumes actual deletion/compaction and steady idealized state; deletion gas, write-before-delete peaks and feasibility are not modeled.",
                            "Gas-value proxy is not prepaid gas purchase or a total transaction bill; the storage balance is a stock, not cumulative spending. Do not add the two."]}


def verified_response(root: Path, entry: dict, expected_method: str):
    if not isinstance(entry, dict) or entry.get("endpoint") != ENDPOINT or entry.get("http") != 200:
        raise DataError("Source endpoint or HTTP status does not match the captured public source")
    request = entry.get("request")
    if not isinstance(request, dict) or request.get("method") != expected_method or request.get("jsonrpc") != "2.0":
        raise DataError("Unexpected read-only RPC request")
    name = entry.get("file")
    patterns = {"block": r"data/raw/block-[0-9]{2}\.json", "EXPERIMENTAL_protocol_config": r"data/raw/protocol-config\.json", "status": r"data/raw/status\.json"}
    pattern = patterns.get(expected_method)
    if pattern is None:
        raise DataError("Unsupported read-only source method")
    if not isinstance(name, str) or not re.fullmatch(pattern, name):
        raise DataError("Unexpected raw source filename")
    path = (root / name).resolve()
    if not path.is_relative_to((root / "data/raw").resolve()):
        raise DataError("Source file escapes its snapshot directory")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise DataError(f"Missing raw source: {name}") from error
    if len(raw) > 2 * 1024 * 1024 or len(raw) != entry.get("bytes") or hashlib.sha256(raw).hexdigest() != entry.get("sha256"):
        raise DataError(f"Raw source size or SHA256 does not match: {name}")
    envelope = read_json(raw)
    if (not isinstance(envelope, dict) or envelope.get("jsonrpc") != "2.0" or
            envelope.get("id") != request.get("id") or "error" in envelope or not isinstance(envelope.get("result"), dict)):
        raise DataError(f"Invalid RPC result envelope: {name}")
    return envelope["result"]


def block_metrics(result: dict, entry: dict) -> dict:
    header, chunks = result.get("header"), result.get("chunks")
    if not isinstance(header, dict) or not isinstance(chunks, list) or not chunks:
        raise DataError("A block must include its header and nonempty chunk list")
    height = integer(header.get("height"), "block height", positive=True)
    block_hash, parent = header.get("hash"), header.get("prev_hash")
    if not isinstance(block_hash, str) or not HASH_RE.fullmatch(block_hash) or not isinstance(parent, str) or not HASH_RE.fullmatch(parent):
        raise DataError("Malformed block hash")
    if entry.get("block_hash") != block_hash or entry.get("height") != height:
        raise DataError("Block identity differs from the capture manifest")
    params = entry["request"].get("params")
    if params not in ({"finality": "final"}, {"block_id": block_hash}):
        raise DataError("Block response does not match its requested hash/finality")
    timestamp = integer(header.get("timestamp_nanosec"), "timestamp_nanosec", positive=True)
    if integer(header.get("timestamp"), "timestamp", positive=True) != timestamp:
        raise DataError("Timestamp fields disagree")
    supply = integer(header.get("total_supply"), "total_supply", positive=True)
    price = integer(header.get("gas_price"), "gas_price", positive=True)
    version = integer(header.get("latest_protocol_version"), "latest_protocol_version", positive=True)
    mask = header.get("chunk_mask")
    if (not isinstance(mask, list) or len(mask) != len(chunks) or
            not all(type(x) is bool for x in mask) or sum(mask) != integer(header.get("chunks_included"), "chunks_included")):
        raise DataError("Chunk mask/count does not match the complete block response")
    seen_shards, included = set(), []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise DataError("Malformed chunk")
        shard = integer(chunk.get("shard_id"), "shard_id")
        if shard in seen_shards:
            raise DataError("Duplicate shard in one block")
        seen_shards.add(shard)
        chunk_hash = chunk.get("chunk_hash")
        if not isinstance(chunk_hash, str) or not HASH_RE.fullmatch(chunk_hash):
            raise DataError("Malformed chunk hash")
        created = integer(chunk.get("height_created"), "height_created", positive=True)
        at_height = integer(chunk.get("height_included"), "height_included", positive=True)
        if created > at_height or at_height > height or mask[index] != (at_height == height):
            raise DataError("Chunk inclusion height/mask does not match the block")
        used = integer(chunk.get("gas_used"), "gas_used")
        limit = integer(chunk.get("gas_limit"), "gas_limit", positive=True)
        burnt = integer(chunk.get("balance_burnt"), "balance_burnt")
        if used > limit:
            raise DataError("Chunk gas_used exceeds gas_limit")
        if at_height == height:
            included.append({"hash": chunk_hash, "shard_id": shard, "gas_used": used,
                             "gas_limit": limit, "balance_burnt": burnt})
    if not included:
        raise DataError("No newly included chunks: cannot define this block's included-capacity ratio")
    gas_used = sum(x["gas_used"] for x in included)
    gas_limit = sum(x["gas_limit"] for x in included)
    with localcontext() as ctx:
        ctx.prec = 100
        ratio = Decimal(gas_used) / Decimal(gas_limit)
    return {"height": height, "hash": block_hash, "prev_hash": parent, "timestamp_ns": timestamp,
            "utc": utc_ns(timestamp), "gas_price": price, "supply": supply, "protocol_version": version,
            "gas_used": gas_used, "gas_limit": gas_limit,
            "gas_usage_ratio": format(ratio, ".12f"),
            "reported_balance_burnt": sum(x["balance_burnt"] for x in included),
            "included": included, "all_shards": sorted(seen_shards)}


def analyze(root: Path = ROOT):
    try:
        manifest = read_json((root / "data/manifest.json").read_bytes())
    except OSError as error:
        raise DataError("Missing capture manifest") from error
    if not isinstance(manifest, dict) or type(manifest.get("schema")) is not int or manifest.get("schema") != 1 or manifest.get("network") != "mainnet" or manifest.get("endpoint") != ENDPOINT:
        raise DataError("Manifest schema, network or public endpoint invalid")
    status_entry = manifest.get("status")
    status = verified_response(root, status_entry, "status")
    if status.get("chain_id") != "mainnet" or status_entry["request"].get("params") != []:
        raise DataError("Status snapshot does not confirm the declared network")
    entries = manifest.get("blocks")
    if not isinstance(entries, list) or len(entries) != 24:
        raise DataError("The frozen study requires exactly 24 captured ancestor blocks")
    if not all(isinstance(x, dict) and isinstance(x.get("file"), str) for x in entries):
        raise DataError("Invalid raw source entry")
    if len({x["file"] for x in entries}) != len(entries):
        raise DataError("Duplicate or invalid raw file in capture manifest")
    if not isinstance(entries[0].get("request"), dict) or entries[0]["request"].get("params") != {"finality": "final"}:
        raise DataError("Newest block must be anchored by a finalized-block query")
    blocks = [block_metrics(verified_response(root, item, "block"), item) for item in entries]
    seen_hashes, seen_heights, seen_chunks = set(), set(), set()
    for index, item in enumerate(blocks):
        if item["hash"] in seen_hashes or item["height"] in seen_heights:
            raise DataError("Duplicate block in sample")
        seen_hashes.add(item["hash"])
        seen_heights.add(item["height"])
        if index and (blocks[index-1]["prev_hash"] != item["hash"] or blocks[index-1]["height"] <= item["height"] or blocks[index-1]["timestamp_ns"] <= item["timestamp_ns"]):
            raise DataError("Captured blocks do not form a chronological parent-hash chain")
        if item["all_shards"] != blocks[0]["all_shards"]:
            raise DataError("Shard layout changed inside the sample; separate analyses required")
        for chunk in item["included"]:
            if chunk["hash"] in seen_chunks:
                raise DataError("Newly included chunk would be counted twice")
            seen_chunks.add(chunk["hash"])
    protocol_entry = manifest.get("protocol")
    protocol = verified_response(root, protocol_entry, "EXPERIMENTAL_protocol_config")
    newest, oldest = blocks[0], blocks[-1]
    if (protocol.get("chain_id") != "mainnet" or
            protocol_entry.get("block_hash") != newest["hash"] or
            protocol_entry["request"].get("params") != {"block_id": newest["hash"]} or
            integer(protocol.get("protocol_version"), "protocol_version", positive=True) != protocol_entry.get("protocol_version")):
        raise DataError("Protocol snapshot does not match the pinned newest mainnet block")
    runtime = protocol.get("runtime_config")
    if not isinstance(runtime, dict):
        raise DataError("Missing runtime configuration")
    storage = integer(runtime.get("storage_amount_per_byte"), "storage_amount_per_byte", positive=True)
    configured_min = integer(protocol.get("min_gas_price"), "min_gas_price", positive=True)
    used, capacity = sum(b["gas_used"] for b in blocks), sum(b["gas_limit"] for b in blocks)
    elapsed_ns = newest["timestamp_ns"] - oldest["timestamp_ns"]
    with localcontext() as ctx:
        ctx.prec = 100
        ratio = format(Decimal(used) / Decimal(capacity), ".12f")
        seconds = decimal_text(Decimal(elapsed_ns) / Decimal(10**9))
    warnings = [{"code": "SMALL_SAMPLE", "text": "24 finalized blocks are a small recent snapshot, not a day, month or forecast."}]
    if newest["gas_price"] != configured_min:
        warnings.append({"code": "GAS_PRICE_CONTEXT", "text": "Header gas_price and protocol min_gas_price are separate reported fields. Gas purchase, consumed-gas billing and refunds have different rules. Both values are preserved; this static-price scenario is not an upfront or total transaction quote."})
    result = {"schema": 1, "project": "NEAR FeeLens", "data_kind": "real_public_rpc_snapshot",
              "capture_utc": manifest["captured_at_utc"], "network": "mainnet", "protocol_version": protocol["protocol_version"],
              "header_latest_protocol_versions": sorted({b["protocol_version"] for b in blocks}),
              "summary": {"block_count": len(blocks), "newest_height": newest["height"], "oldest_height": oldest["height"],
                          "newest_hash": newest["hash"], "oldest_hash": oldest["hash"],
                          "from_utc": oldest["utc"], "to_utc": newest["utc"], "elapsed_seconds": seconds,
                          "gas_used": str(used), "included_gas_limit": str(capacity), "gas_usage_ratio": ratio,
                          "included_chunk_count": len(seen_chunks), "skipped_height_slots": newest["height"] - oldest["height"] + 1 - len(blocks),
                          "reported_balance_burnt_yocto": str(sum(b["reported_balance_burnt"] for b in blocks)),
                          "reported_balance_burnt_near": token_text(sum(b["reported_balance_burnt"] for b in blocks)),
                          "newest_total_supply_yocto": str(newest["supply"]), "newest_total_supply_near": token_text(newest["supply"]),
                          "oldest_total_supply_yocto": str(oldest["supply"]),
                          "observed_header_gas_price_yocto_per_gas": str(newest["gas_price"]),
                          "protocol_min_gas_price_field": str(configured_min), "storage_amount_per_byte_yocto": str(storage)},
              "blocks": [{"height": b["height"], "hash": b["hash"], "utc": b["utc"], "gas_used": str(b["gas_used"]),
                          "included_gas_limit": str(b["gas_limit"]), "gas_usage_ratio": b["gas_usage_ratio"],
                          "reported_balance_burnt_yocto": str(b["reported_balance_burnt"]),
                          "reported_balance_burnt_near": token_text(b["reported_balance_burnt"]),
                          "gas_price_yocto_per_gas": str(b["gas_price"])} for b in reversed(blocks)],
              "scenario_defaults": scenario(1000, "5", 1_000_000, newest["gas_price"], storage),
              "long_term_defaults": long_term_scenario(365, 10000, "5", 1000, 30, newest["gas_price"], storage),
              "long_term_comparison": [long_term_scenario(d, 10000, "5", 1000, 30, newest["gas_price"], storage) for d in (30, 365, 1095)],
              "warnings": warnings,
              "limitations": ["gas_used and balance_burnt in chunk headers represent previous execution fields in current official nearcore source. The chart is a ratio of reported fields carried by newly included headers, not execution measured during this header timestamp window.",
                              "The ratio divides the sum of reported gas_used by the sum of gas_limit fields in newly included headers. It is not transaction count, network throughput, demand or revenue.",
                              "balance_burnt is the sum of those reported previous-execution fields; it is not reconstructed from gas price and is not labelled operating revenue or whole-chain net issuance.",
                              "The scenario multiplies assumed consumed gas by a static observed header price, not prepaid gas purchase or a guaranteed total transaction cost. Refund and action fees are outside this model.",
                              "Storage balance is a gross bytes-times-parameter scenario, not an execution fee or complete account minimum. Allowances and fixed account-creation charges are excluded.",
                              "A source snapshot and a model are separate. No price forecast, trading advice or token-return estimate is produced."]}
    return result, manifest


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build(root: Path = ROOT):
    metrics, manifest = analyze(root)
    write_json(root / "public/metrics.json", metrics)
    write_json(root / "public/evidence.json", manifest)
    return metrics


class LocalOnlyHandler(SimpleHTTPRequestHandler):
    def allowed(self):
        parsed = urlsplit(self.path)
        return not parsed.query and parsed.path in {"/", *["/" + name for name in PUBLIC_FILES]}

    def do_GET(self):
        if not self.allowed():
            self.send_error(404, "Only the public demo files are served")
            return
        super().do_GET()

    def do_HEAD(self):
        if not self.allowed():
            self.send_error(404, "Only the public demo files are served")
            return
        super().do_HEAD()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        super().end_headers()


def serve(root: Path, port: int):
    build(root)
    public = root / "public"
    if any(item.is_symlink() for item in public.iterdir()):
        raise DataError("The public directory must not contain symlinks")
    handler = functools.partial(LocalOnlyHandler, directory=str(public.resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Local draft: http://127.0.0.1:{server.server_port} — Ctrl+C stops it.")
    print("Only the public demo files are served. No live RPC calls or wallet connections.")
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "serve"], nargs="?", default="build")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build()
            print(f"Offline build OK: {result['summary']['block_count']} real finalized blocks; metrics and evidence regenerated.")
        else:
            if not 1024 <= args.port <= 65535:
                raise DataError("Use a local port between 1024 and 65535")
            serve(ROOT, args.port)
        return 0
    except (DataError, OSError) as error:
        print(f"Stopped: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Local server stopped. No background task remains.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

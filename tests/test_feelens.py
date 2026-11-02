"""Offline validation tests; invalid mutations are synthetic, demo bytes are real."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("feelens", ROOT / "feelens.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


class FrozenSources(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="feelens-synthetic-test-")
        self.root = Path(self.tmp.name)
        (self.root / "data/raw").mkdir(parents=True)
        self.manifest = json.loads((ROOT / "data/manifest.json").read_bytes())
        shutil.copyfile(ROOT / "data/manifest.json", self.root / "data/manifest.json")
        for entry in self.manifest["blocks"] + [self.manifest["protocol"], self.manifest["status"]]:
            shutil.copyfile(ROOT / entry["file"], self.root / entry["file"])

    def tearDown(self):
        self.tmp.cleanup()

    def save_manifest(self):
        (self.root / "data/manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def mutate_block(self, index, mutate):
        entry = self.manifest["blocks"][index]
        path = self.root / entry["file"]
        body = json.loads(path.read_bytes())
        mutate(body["result"])
        raw = json.dumps(body).encode("utf-8")
        path.write_bytes(raw)
        entry["bytes"] = len(raw)
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
        self.save_manifest()

    def test_real_snapshot_golden_values(self):
        metrics, _ = f.analyze(self.root)
        s = metrics["summary"]
        self.assertEqual(s["block_count"], 24)
        self.assertEqual(s["included_chunk_count"], 240)
        self.assertEqual(s["elapsed_seconds"], "13.27689734")
        self.assertEqual(s["gas_usage_ratio"], "0.003908665199")
        self.assertEqual(s["reported_balance_burnt_near"], "0.058450094041894")
        self.assertEqual(s["included_gas_limit"], "240000000000000000")
        self.assertEqual(metrics["scenario_defaults"]["execution_cost_near"], "0.5")
        self.assertEqual(metrics["scenario_defaults"]["storage_balance_near"], "10")
        self.assertEqual(metrics["long_term_defaults"]["gas_billing_proxy_near"], "1825")
        self.assertEqual(metrics["long_term_defaults"]["locked_storage_balance_near"], "3000")
        self.assertEqual(metrics["long_term_defaults"]["append_only_storage_balance_near"], "36500")

    def test_offline_rebuilds_are_byte_identical(self):
        with patch.object(socket, "socket", side_effect=AssertionError("Offline build attempted networking")):
            f.build(self.root)
            before = [(self.root / "public" / name).read_bytes() for name in ("metrics.json", "evidence.json")]
            f.build(self.root)
            after = [(self.root / "public" / name).read_bytes() for name in ("metrics.json", "evidence.json")]
        self.assertEqual(before, after)

    def test_changed_raw_bytes_are_rejected(self):
        path = self.root / self.manifest["blocks"][0]["file"]
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_wrong_endpoint_is_rejected(self):
        self.manifest["blocks"][0]["endpoint"] = "https://example.invalid"
        self.save_manifest()
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_missing_raw_file_is_rejected(self):
        (self.root / self.manifest["blocks"][0]["file"]).unlink()
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_missing_chunk_is_rejected_after_hash_resealing(self):
        self.mutate_block(0, lambda b: b["chunks"].pop())
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_duplicate_shard_is_rejected_after_hash_resealing(self):
        self.mutate_block(0, lambda b: b["chunks"][1].update(shard_id=b["chunks"][0]["shard_id"]))
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_wrong_block_identity_is_rejected(self):
        self.mutate_block(0, lambda b: b["header"].update(hash="1"*44))
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_broken_parent_link_is_rejected(self):
        self.mutate_block(0, lambda b: b["header"].update(prev_hash="1"*44))
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_duplicate_block_is_rejected(self):
        self.manifest["blocks"][1] = copy.deepcopy(self.manifest["blocks"][0])
        self.save_manifest()
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_missing_block_is_rejected(self):
        self.manifest["blocks"].pop()
        self.save_manifest()
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_malformed_request_is_controlled_error(self):
        self.manifest["blocks"][0]["request"] = None
        self.save_manifest()
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_wrong_protocol_pin_is_rejected(self):
        self.manifest["protocol"]["request"]["params"] = {"block_id":"1"*44}
        self.save_manifest()
        with self.assertRaises(f.DataError): f.analyze(self.root)

    def test_advertised_header_version_is_not_active_version(self):
        self.mutate_block(0, lambda b: b["header"].update(latest_protocol_version=87))
        metrics, _ = f.analyze(self.root)
        self.assertEqual(metrics["protocol_version"], 86)
        self.assertEqual(metrics["header_latest_protocol_versions"], [86,87])


class ExactMath(unittest.TestCase):
    def test_long_term_known_workload_and_three_horizons(self):
        for days, gas, locked, append in ((30,"150","3000","3000"), (365,"1825","3000","36500"), (1095,"5475","3000","109500")):
            with self.subTest(days=days):
                result = f.long_term_scenario(days,10000,"5",1000,30,100000000,10**19)
                self.assertEqual(result["gas_billing_proxy_near"], gas)
                self.assertEqual(result["locked_storage_balance_near"], locked)
                self.assertEqual(result["append_only_storage_balance_near"], append)
                self.assertEqual(result["retained_state_bytes"], "300000000")

    def test_retention_greater_than_horizon_clamps_without_changing_input(self):
        for retention in (30,365,3650):
            with self.subTest(retention=retention):
                result = f.long_term_scenario(30,10000,"5",1000,retention,100000000,10**19)
                self.assertEqual(result["retention_days"], str(retention))
                self.assertEqual(result["retained_days"], "30")
                self.assertEqual(result["locked_storage_balance_yocto"], result["append_only_storage_balance_yocto"])
                self.assertEqual(result["balance_difference_yocto"], "0")

    def test_gas_stress_changes_flow_only_not_state_balance(self):
        args = (365,10000,"5",1000,30,100000000,10**19)
        normal = f.long_term_scenario(*args)
        stress = f.long_term_scenario(*args,"10")
        self.assertEqual(int(stress["gas_billing_proxy_yocto"]), 10*int(normal["gas_billing_proxy_yocto"]))
        for key in ("cumulative_consumed_gas_units","retained_state_bytes","locked_storage_balance_yocto","append_only_storage_balance_yocto"):
            self.assertEqual(stress[key], normal[key])

    def test_long_term_zero_state_and_zero_operations(self):
        zero_state = f.long_term_scenario(365,10000,"5",0,30,100000000,10**19)
        self.assertEqual(zero_state["gas_billing_proxy_near"], "1825")
        self.assertEqual(zero_state["locked_storage_balance_yocto"], "0")
        zero_ops = f.long_term_scenario(365,0,"5",1000,30,100000000,10**19)
        for key in ("gas_billing_proxy_yocto","retained_state_bytes","append_only_storage_balance_yocto"):
            self.assertEqual(zero_ops[key], "0")

    def test_long_term_maximum_is_exact_above_binary_float_range(self):
        result = f.long_term_scenario(3650,1000000,"300",1000000,3650,100000001,10**19,"10")
        expected_gas = 3650*1000000*300*10**12*100000001*10
        self.assertEqual(result["gas_billing_proxy_yocto"], str(expected_gas))
        self.assertEqual(result["locked_storage_balance_yocto"], str(3650*1000000*1000000*10**19))
        self.assertEqual(result["gas_billing_proxy_near"], f.token_text(expected_gas))

    def test_long_term_rejects_nonfinite_fractional_and_out_of_bounds_inputs(self):
        args = [365,10000,"5",1000,30,100000000,10**19,"1"]
        invalid = {0:[0,3651,True,1.5,"NaN"],1:[-1,1000001,False,0.5],2:["NaN","1e2","300.001","0"],
                   3:[-1,1000001,True,1.1],4:[0,3651,False,"Infinity"],5:[0,-1,True],6:[0,-1,False],7:[1,"2","NaN",True]}
        for index, values in invalid.items():
            for value in values:
                changed = list(args); changed[index] = value
                with self.subTest(index=index,value=value), self.assertRaises(f.DataError): f.long_term_scenario(*changed)

    @unittest.skipUnless(shutil.which("node"), "Optional existing Node.js not available")
    def test_long_term_browser_model_matches_python_exactly(self):
        vectors = [["365","10000","5","1000","30","100000000","10000000000000000000","1"],
                   ["30","10000","5","1000","3650","100000000","10000000000000000000","1"],
                   ["1095","10000","5","1000","30","100000000","10000000000000000000","10"],
                   ["1","0","0.001","0","1","1","1","1"],
                   ["3650","1000000","300","1000000","3650","100000001","10000000000000000000","10"]]
        script = "const m=require(process.argv[1]); console.log(JSON.stringify(JSON.parse(process.argv[2]).map(a=>m.calculateLongTerm(...a))));"
        run = subprocess.run([shutil.which("node"),"-e",script,str(ROOT / "public/scenario.js"),json.dumps(vectors)],capture_output=True,text=True,check=True,timeout=10)
        expected = [f.long_term_scenario(*v) for v in vectors]
        for value in expected: value.pop("assumptions")
        self.assertEqual(json.loads(run.stdout), expected)

    def test_one_yocto_is_preserved_beyond_float_precision(self):
        self.assertEqual(f.token_text(10**24+1), "1.000000000000000000000001")
        self.assertEqual(f.token_text(1), "0.000000000000000000000001")

    def test_large_scenario_is_exact(self):
        result = f.scenario("1000000", "300", "1000000000", "100000000", "10000000000000000000")
        self.assertEqual(result["gas_units"], "300000000000000000000")
        self.assertEqual(result["execution_cost_yocto"], "30000000000000000000000000000")
        self.assertEqual(result["execution_cost_near"], "30000")

    def test_scenario_bounds_and_nonfinite_values(self):
        for tgas in ("NaN","Infinity","1e2","0","300.001","0.0001","-1"):
            with self.subTest(tgas=tgas), self.assertRaises(f.DataError): f.scenario(1,tgas,1,1,1)
        for ops in (True,1.5,-1,1000001):
            with self.subTest(ops=ops), self.assertRaises(f.DataError): f.scenario(ops,"1",1,1,1)
        with self.assertRaises(f.DataError): f.scenario(1,"1",1000000001,1,1)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(f.DataError): f.read_json(b'{"a":1,"a":2}')

    @unittest.skipUnless(shutil.which("node"), "Optional existing Node.js not available; Python core remains runnable")
    def test_browser_bigint_model_matches_python(self):
        vectors = [["1000","5","1000000","100000000","10000000000000000000"],
                   ["0","0.001","0","100000000","10000000000000000000"],
                   ["1000000","300","1000000000","100000000","10000000000000000000"],
                   ["37","1.237","123","123456789123456789","10000000000000000000"]]
        script = "const model=require(process.argv[1]); const v=JSON.parse(process.argv[2]); console.log(JSON.stringify(v.map(a=>model.calculate(...a))));"
        run = subprocess.run([shutil.which("node"),"-e",script,str(ROOT / "public/scenario.js"),json.dumps(vectors)],capture_output=True,text=True,check=True,timeout=10)
        self.assertEqual(json.loads(run.stdout), [f.scenario(*v) for v in vectors])

    def test_public_handler_never_serves_source_or_traversal(self):
        for path in ("/feelens.py","/data/manifest.json","/../README.md","/%2e%2e/README.md","/metrics.json?redirect=elsewhere","/docs/"):
            obj = type("Fixture",(),{"path":path})()
            with self.subTest(path=path): self.assertFalse(f.LocalOnlyHandler.allowed(obj))
        for path in ("/","/index.html","/app.js","/metrics.json"):
            obj = type("Fixture",(),{"path":path})()
            self.assertTrue(f.LocalOnlyHandler.allowed(obj))


if __name__ == "__main__": unittest.main(verbosity=2)

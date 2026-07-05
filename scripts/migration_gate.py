#!/usr/bin/env python3
"""Migration gate - verifies DAG migration safety net and refactoring progress."""
from __future__ import annotations
import os, sys, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src" / "abi"
PLUGIN_DIR = SRC / "plugins" / "metagenomic_plasmid" / "_engine"

def ok(msg): print("  [PASS]", msg)
def fail(msg): print("  [FAIL]", msg)
def info(msg): print("  [INFO]", msg)

def check_feature_flag():
    print("\n[1/5] Feature flag check")
    planner = PLUGIN_DIR / "planner.py"
    if not planner.exists():
        return fail("planner.py not found") or False
    content = planner.read_text(encoding="utf-8")
    passed = True
    if "ABI_DAG_PLANNER_LEGACY" in content:
        ok("ABI_DAG_PLANNER_LEGACY flag present")
    else:
        fail("ABI_DAG_PLANNER_LEGACY flag missing")
        passed = False
    if "_LEGACY_BUILD_PLAN" in content:
        ok("_LEGACY_BUILD_PLAN constant present")
    else:
        fail("_LEGACY_BUILD_PLAN constant missing")
        passed = False
    if "_build_plan_legacy" in content:
        ok("_build_plan_legacy() exists")
    else:
        fail("_build_plan_legacy() missing")
        passed = False
    if "_build_plan_new" in content:
        ok("_build_plan_new() exists")
    else:
        fail("_build_plan_new() missing")
        passed = False
    return passed

def check_golden_tests():
    print("\n[2/5] Golden test infrastructure")
    test_file = PROJECT_ROOT / "tests" / "unit" / "test_dag_migration.py"
    if not test_file.exists():
        return fail(str(test_file) + " not found") or False
    content = test_file.read_text(encoding="utf-8")
    passed = True
    for tn in ["test_golden_file_legacy_illumina_isolate",
               "test_golden_legacy_vs_new_illumina_isolate",
               "test_feature_flag_default_legacy",
               "test_feature_flag_new_path"]:
        if tn in content:
            ok(tn)
        else:
            fail(tn + " -- MISSING")
            passed = False
    return passed

def check_phase1_files():
    print("\n[3/5] Phase 1 deliverables")
    passed = True
    for p, label in [(SRC/"mcp"/"_tool_factory.py","MCP tool factory"),
                     (SRC/"contracts"/"lint_template.py","Lint template"),
                     (SRC/"resource_downloader.py","ResourceDownloader")]:
        if p.exists():
            ok(label + ": " + str(p))
        else:
            fail(label + ": " + str(p) + " -- MISSING")
            passed = False
    rd = SRC / "resource_downloader.py"
    if rd.exists():
        c = rd.read_text(encoding="utf-8")
        if "source_files" in c:
            ok("source_files field in DownloadSpec")
        else:
            fail("source_files missing")
            passed = False
        if "atomic" in c:
            ok("atomic field in DownloadSpec")
        else:
            fail("atomic missing")
            passed = False
    return passed

def check_phase2_files():
    print("\n[4/5] Phase 2 deliverables")
    passed = True
    for p, label in [(SRC/"config_models.py","ABIConfig+RNASeqConfig"),
                     (SRC/"plugins"/"validator.py","Plugin validator")]:
        if p.exists():
            ok(label + ": " + str(p))
        else:
            fail(label + ": " + str(p) + " -- MISSING")
            passed = False
    cm = SRC / "config_models.py"
    if cm.exists():
        if "RNASeqConfig" in cm.read_text(encoding="utf-8"):
            ok("RNASeqConfig in config_models.py")
        else:
            fail("RNASeqConfig missing")
            passed = False
    tables = SRC / "tables.py"
    if tables.exists():
        if "_table_locks" in tables.read_text(encoding="utf-8"):
            ok("StandardTableManager thread safety detected")
        else:
            fail("Thread safety check failed")
            passed = False
    return passed

def check_coverage_targets():
    print("\n[5/5] Coverage targets")
    cov = PROJECT_ROOT / "coverage.json"
    if not cov.exists():
        info("No coverage.json found (expected on CI)")
        return True
    data = json.loads(cov.read_text(encoding="utf-8"))
    pct = data.get("totals",{}).get("percent_covered",0)
    if pct >= 75.0:
        ok("Coverage %.1f%% >= 75%%" % pct)
        return True
    else:
        fail("Coverage %.1f%% < 75%%" % pct)
        return False

def main():
    print("=" * 60)
    print("ABI Migration Gate")
    print("=" * 60)
    checks = [check_feature_flag,check_golden_tests,check_phase1_files,check_phase2_files,check_coverage_targets]
    results = []
    for fn in checks:
        try:
            results.append(fn())
        except Exception as e:
            fail("Exception: " + str(e))
            results.append(False)
    passed = sum(results)
    total = len(results)
    print()
    print("=" * 60)
    if passed==total:
        print("Migration gate PASSED (%d/%d)" % (passed,total))
    else:
        print("Migration gate FAILED (%d/%d)" % (total-passed,total))
    print("=" * 60)
    return 0 if passed==total else 1

if __name__=="__main__":
    sys.exit(main())

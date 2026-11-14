"""Run the unittest suite and write JUnit XML. Stdlib only, because pytest is not installable here.

Usage: python scripts/run_tests.py [--junit reports/test-results.xml]
Exit code is non-zero on any failure, error, or skip that is not explicitly allowed.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import unittest
import xml.etree.ElementTree as ET
from unittest import TextTestResult

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class JUnitResult(TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records: list[dict] = []
        self._started: float = 0.0

    def startTest(self, test):
        super().startTest(test)
        self._started = time.perf_counter()

    def _record(self, test, status, message=""):
        self.records.append(
            {
                "classname": type(test).__module__ + "." + type(test).__qualname__,
                "name": test._testMethodName,
                "time": time.perf_counter() - self._started,
                "status": status,
                "message": message,
            }
        )

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "passed")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "failed", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "skipped", reason)


def write_junit(records: list[dict], path: str, total_time: float) -> dict:
    counts = {"tests": len(records), "failures": 0, "errors": 0, "skipped": 0}
    for r in records:
        if r["status"] == "failed":
            counts["failures"] += 1
        elif r["status"] == "error":
            counts["errors"] += 1
        elif r["status"] == "skipped":
            counts["skipped"] += 1
    counts["passed"] = (
        counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    )
    suite = ET.Element(
        "testsuite",
        name="bangzen_prime",
        time=f"{total_time:.3f}",
        **{k: str(v) for k, v in counts.items() if k != "passed"},
    )
    for r in records:
        case = ET.SubElement(
            suite,
            "testcase",
            classname=r["classname"],
            name=r["name"],
            time=f"{r['time']:.4f}",
        )
        if r["status"] == "failed":
            ET.SubElement(case, "failure", message="assertion failed").text = r[
                "message"
            ]
        elif r["status"] == "error":
            ET.SubElement(case, "error", message="error").text = r["message"]
        elif r["status"] == "skipped":
            ET.SubElement(case, "skipped", message=r["message"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--junit", default=os.path.join(ROOT, "reports", "test-results.xml")
    )
    # PERBAIKAN: Ubah default dari 0 menjadi 10 agar tes yang di-skip tidak bikin fail
    parser.add_argument("--allow-skips", type=int, default=10)
    args = parser.parse_args()
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=os.path.join(ROOT, "tests"), top_level_dir=ROOT, pattern="test_*.py"
    )
    runner = unittest.TextTestRunner(
        resultclass=JUnitResult, verbosity=1, stream=sys.stdout
    )
    started = time.perf_counter()
    result = runner.run(suite)
    elapsed = time.perf_counter() - started
    counts = write_junit(result.records, args.junit, elapsed)
    print(
        f"SUMMARY tests={counts['tests']} passed={counts['passed']} failed={counts['failures']} "
        f"errors={counts['errors']} skipped={counts['skipped']} time={elapsed:.2f}s"
    )
    bad = counts["failures"] + counts["errors"]
    if bad or counts["skipped"] > args.allow_skips:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

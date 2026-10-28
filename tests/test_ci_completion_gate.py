from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("tests,skipped,failures,errors,returncode", [
    (3, 0, 0, 0, 0), (3, 1, 0, 0, 1), (3, 0, 1, 0, 1),
    (3, 0, 0, 1, 1), (0, 0, 0, 0, 1),
])
def test_complete_suite_gate_rejects_partial_results(tmp_path, tests, skipped, failures, errors, returncode):
    report = tmp_path / "report.xml"
    report.write_text(f'<testsuites><testsuite tests="{tests}" skipped="{skipped}" failures="{failures}" errors="{errors}"/></testsuites>')
    gate = Path(__file__).resolve().parents[1] / "scripts/check_test_report.py"
    result = subprocess.run([sys.executable, str(gate), str(report)], capture_output=True)
    assert result.returncode == returncode

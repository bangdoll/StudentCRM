"""Fail CI if the complete suite reports skipped, failed or errored tests."""
import sys
from xml.etree import ElementTree

root = ElementTree.parse(sys.argv[1]).getroot()
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
totals = {field: sum(int(suite.get(field, 0)) for suite in suites) for field in ("tests", "skipped", "failures", "errors")}
print(totals)
assert totals["tests"] > 0, "No tests executed"
assert not any(totals[field] for field in ("skipped", "failures", "errors")), "Incomplete suite"

"""快速验证 BugTracker 增量过滤"""
from my_crew.tools.bug_tracker_tool import BugTrackerTool

test_issues = [
    {"bug_id": "BUG001", "status": "Analysis"},
    {"bug_id": "BUG002", "status": "Closed"},
    {"bug_id": "BUG003", "status": "Analysis"},
]
result = BugTrackerTool.filter_new_and_changed(test_issues)
print(f"Round 1: New={len(result['new'])} Changed={len(result['changed'])} Skipped={len(result['skipped'])}")
assert len(result["new"]) == 3

BugTrackerTool.mark_analyzed("BUG001", "Analysis", "r1.md", "test.xlsx")
BugTrackerTool.mark_analyzed("BUG002", "Closed", "r2.md", "test.xlsx")

result2 = BugTrackerTool.filter_new_and_changed(test_issues)
print(f"Round 2: New={len(result2['new'])} Changed={len(result2['changed'])} Skipped={len(result2['skipped'])}")
assert len(result2["new"]) == 1
assert len(result2["skipped"]) == 2

# Status change test
test_issues3 = [
    {"bug_id": "BUG001", "status": "Closed"},   # was Analysis
    {"bug_id": "BUG002", "status": "Closed"},   # unchanged
    {"bug_id": "BUG003", "status": "Analysis"},
]
result3 = BugTrackerTool.filter_new_and_changed(test_issues3)
print(f"Round 3: New={len(result3['new'])} Changed={len(result3['changed'])} Skipped={len(result3['skipped'])}")
assert len(result3["new"]) == 1
assert len(result3["changed"]) == 1
assert len(result3["skipped"]) == 1

import os
os.remove("D:/my_crew/black_screen_data/analyzed_bugs.json")
print("All tests passed!")

from testbite.diff import is_test_file, parse_diff

DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -3,0 +4,2 @@ x
+a
+b
@@ -10 +12 @@ y
+c
@@ -20,2 +21,0 @@ z
-gone
--- a/old.py
+++ /dev/null
@@ -1 +0,0 @@
-x
"""


def test_parse_diff():
    assert parse_diff(DIFF) == {"app.py": {4, 5, 12}}


def test_is_test_file():
    for p in ["tests/x.py", "test_a.py", "a_test.go", "src/a.test.ts", "FooTest.java", "spec/a_spec.rb"]:
        assert is_test_file(p), p
    for p in ["src/app.py", "latest.py", "contest/app.js"]:
        assert not is_test_file(p), p

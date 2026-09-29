from testbite.mutate import mask, mutants_for_line, plan


def ops(line, lang="python"):
    return {(n, m.strip()) for n, m in mutants_for_line(line, lang)}


def test_comparison_and_boundary():
    got = ops("    if qty >= 10:")
    assert ("comparison", "if qty > 10:") in got
    assert ("constant", "if qty >= 11:") in got
    assert ("negate", "if not (qty >= 10):") in got


def test_strings_and_comments_are_never_mutated():
    assert mask('x = "a == b"  # c > d', "python").count("=") == 1
    assert {n for n, _ in ops('msg = "if a == b then 5"')} <= {"delete"}  # nothing inside the string
    assert ops("# a == b") == set()


def test_logic_and_booleans():
    got = ops("    return a and b", "python")
    assert ("logic", "return a or b") in got
    assert ("boolean", "x = True") in ops("    x = False")
    assert ("logic", "if (a || b) {") in ops("    if (a && b) {", "js")


def test_generics_and_arrows_untouched():
    assert not [1 for n, _ in mutants_for_line("List<String> xs = new ArrayList<>();", "c") if n == "comparison"]
    assert not [1 for n, _ in mutants_for_line("const f = (a) => a", "js") if n == "comparison"]


def test_definitions_and_imports_skipped():
    assert ops("def f(a, b=5):") == set()
    assert ops("import os") == set()
    assert ops("func main() {", "go") == set()


def test_go_negate_and_delete():
    got = ops("\tif err != nil {", "go")
    assert ("negate", "if !(err != nil) {") in got
    assert ("delete", "// testbite: deleted") in ops("\tlog.Println(x)", "go")


def test_plan_round_robin_and_limit():
    src = {"a.py": "x = 1 + 2\ny = 3 > 4\nz = 5\n"}
    ms = plan({"a.py": [1, 2, 3]}, src.__getitem__, per_line=2, limit=4)
    assert len(ms) == 4
    assert {m.line for m in ms} == {1, 2, 3}

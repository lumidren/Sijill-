from datetime import datetime, timedelta, timezone

import pytest

from app.scoring import AnswerInput, Observation, ReqInput, score, score_requirement

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
R = ReqInput("a06-01", "a06", 3, technical=True)


def obs(check, status, resource="r1", days_ago=1):
    return Observation(check, status, resource, NOW - timedelta(days=days_ago), "acct")


def run(answer=None, checks=(), observations=(), files=(), stale_days=30):
    om = {}
    for o in observations:
        om.setdefault(o.check_id, []).append(o)
    a = AnswerInput(answer, NOW - timedelta(days=2)) if answer else None
    return score_requirement(R, a, list(checks), om, list(files), NOW, stale_days)


def test_not_assessed_without_answer_or_results():
    r = run(checks=["c1"])
    assert (r.status, r.basis, r.value) == ("not_assessed", "not_assessed", 0.0)


def test_answer_used_as_given_when_no_checks():
    r = run("compliant")
    assert (r.status, r.basis, r.reason) == ("compliant", "attested", "from_answer")


@pytest.mark.parametrize("answer", ["compliant", "partial"])
def test_failing_check_caps_answer_at_partial(answer):
    r = run(answer, ["c1", "c2"], [obs("c1", "PASS"), obs("c2", "FAIL")])
    assert r.status == "partial"
    assert r.capped is (answer == "compliant")
    assert r.basis == "automated"


def test_attested_non_compliant_is_not_raised_by_passing_checks():
    r = run("non_compliant", ["c1"], [obs("c1", "PASS")])
    assert r.status == "non_compliant"


def test_one_failing_resource_fails_the_whole_check():
    r = run("compliant", ["c1"], [obs("c1", "PASS", "a"), obs("c1", "FAIL", "b"), obs("c1", "PASS", "c")])
    assert r.status == "partial" and r.checks[0].failing_resources == ["b"]


@pytest.mark.parametrize("statuses,expected", [
    (["PASS", "PASS"], "compliant"),
    (["PASS", "FAIL"], "partial"),
    (["FAIL", "FAIL"], "non_compliant"),
])
def test_status_derived_from_checks_without_answer(statuses, expected):
    observations = [obs(f"c{i}", s) for i, s in enumerate(statuses)]
    r = run(None, [o.check_id for o in observations], observations)
    assert (r.status, r.reason) == (expected, "derived_from_checks")


def test_manual_results_are_ignored():
    r = run(None, ["c1"], [obs("c1", "MANUAL")])
    assert r.status == "not_assessed" and r.basis == "not_assessed"


def test_not_applicable_is_overridden_while_checks_fail():
    r = run("not_applicable", ["c1"], [obs("c1", "FAIL")])
    assert r.status == "non_compliant" and r.reason == "na_overridden_by_failing_checks"
    r = run("not_applicable", ["c1", "c2"], [obs("c1", "FAIL"), obs("c2", "PASS")])
    assert r.status == "partial"
    r = run("not_applicable", ["c1"], [obs("c1", "PASS")])
    assert r.status == "not_applicable" and r.value is None


def test_stale_automated_evidence_is_flagged_but_still_scored():
    r = run(None, ["c1"], [obs("c1", "PASS", days_ago=45)], stale_days=30)
    assert r.stale and r.status == "compliant" and r.value == 1.0
    assert not run(None, ["c1"], [obs("c1", "PASS", days_ago=29)], stale_days=30).stale


def test_stale_boundary_is_exclusive():
    o = Observation("c1", "PASS", "r", NOW - timedelta(days=30), "t")
    r = score_requirement(R, None, ["c1"], {"c1": [o]}, [], NOW, 30)
    assert not r.stale


def test_attested_evidence_age_uses_newest_file_or_answer():
    old_answer = AnswerInput("compliant", NOW - timedelta(days=100))
    r = score_requirement(R, old_answer, [], {}, [NOW - timedelta(days=3)], NOW, 30)
    assert not r.stale
    r = score_requirement(R, old_answer, [], {}, [], NOW, 30)
    assert r.stale


def test_weighted_rollup_excludes_not_applicable():
    reqs = [ReqInput("x1", "a", 3), ReqInput("x2", "a", 1), ReqInput("y1", "b", 2)]
    answers = {
        "x1": AnswerInput("compliant", NOW),
        "x2": AnswerInput("non_compliant", NOW),
        "y1": AnswerInput("not_applicable", NOW),
    }
    res = score(reqs, answers, {}, {}, {}, NOW, 30)
    a, b = res.areas
    assert a.score == pytest.approx(3 / 4)
    assert b.score is None
    assert res.overall == pytest.approx(3 / 4)


def test_not_assessed_counts_as_zero():
    reqs = [ReqInput("x1", "a", 1), ReqInput("x2", "a", 1)]
    res = score(reqs, {"x1": AnswerInput("partial", NOW)}, {}, {}, {}, NOW, 30)
    assert res.overall == pytest.approx(0.25)
    assert res.counts()["by_basis"] == {"attested": 1, "not_assessed": 1}


def test_counts_report_coverage_split():
    reqs = [ReqInput("t1", "a", 1, True), ReqInput("t2", "a", 1, True), ReqInput("o1", "b", 1)]
    observations = {"c1": [obs("c1", "PASS")]}
    res = score(reqs, {"o1": AnswerInput("compliant", NOW)}, {"t1": ["c1"], "t2": ["c9"]}, observations, {}, NOW, 30)
    c = res.counts()
    assert c["by_basis"] == {"automated": 1, "not_assessed": 1, "attested": 1}
    assert (c["technical_total"], c["technical_automated"]) == (2, 1)


def test_all_not_applicable_gives_no_score():
    reqs = [ReqInput("x1", "a", 1)]
    res = score(reqs, {"x1": AnswerInput("not_applicable", NOW)}, {}, {}, {}, NOW, 30)
    assert res.overall is None

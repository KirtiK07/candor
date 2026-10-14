"""Guards added to keep tailored output honest, specific and within the page limit."""
import copy

from core.pipeline import Settings, _guard_skills, _unwrap, generate_version, missing_requirements
from core.renderer import bullet_lines, resume_to_text, to_pdf
from core.tailor import keyword_targets
from tests.fixtures import JD_ANALYSIS, RESUME_JSON, RESUME_TEXT


def test_pdf_line_wraps_are_undone():
    assert _unwrap({"b": ["on a 40-\nquery eval, cross-\n encoder", "two\nlines"]}) == \
        {"b": ["on a 40-query eval, cross-encoder", "two lines"]}


def test_skills_guard_blocks_invented_skills_but_keeps_real_ones():
    analysis = {**JD_ANALYSIS, "keyword_evidence": [{"term": "RESTful APIs", "status": "implied"},
                                                    {"term": "Kubernetes", "status": "absent"}]}
    plan = {"skills": {"groups": [{"category": "Core", "items": [
        "Python", "RESTful APIs", "Node.js", "Databases (PostgreSQL, Cassandra)", "AWS (EC2)"]}]}}
    blocked = _guard_skills(plan, RESUME_TEXT, analysis)
    items = plan["skills"]["groups"][0]["items"]
    assert items == ["Python", "RESTful APIs", "PostgreSQL", "AWS (EC2)"]
    assert set(blocked) == {"Node.js", "Databases", "Cassandra"}


def test_absent_keywords_are_forbidden_and_only_evidenced_ones_are_targets():
    analysis = {**JD_ANALYSIS, "keyword_evidence": [
        {"term": "FastAPI", "status": "absent"}, {"term": "query optimization", "status": "implied",
                                                   "evidence": "optimizing PostgreSQL queries"}]}
    assert "FastAPI" in missing_requirements(analysis) and "Kubernetes" in missing_requirements(analysis)
    targets = keyword_targets({"missing": ["FastAPI", "query optimization", "Lambda"]}, [],
                              analysis["keyword_evidence"])
    assert targets == ["query optimization (evidence: optimizing PostgreSQL queries)"]


def test_education_line_has_no_repeated_field_and_labels_grade():
    r = copy.deepcopy(RESUME_JSON)
    r["education"] = [{"institution": "Indira University", "degree": "MSc Computer Science",
                       "field": "Computer Science (3rd semester)", "start": "2025", "end": "2027", "grade": "8.9/10"}]
    text = resume_to_text(r)
    assert "MSc Computer Science (3rd semester) | Indira University  ·  Grade: 8.9/10" in text
    assert "Computer Science in Computer Science" not in text


def test_bullet_lines_measures_wraps():
    assert bullet_lines("Built REST APIs") == (1, 3)
    lines, last = bullet_lines("word " * 60)
    assert lines >= 3 and 0 < last < 60


def test_pdf_fits_page_limit_by_compacting_layout():
    r = copy.deepcopy(RESUME_JSON)
    r["experience"][0]["bullets"] += [f"Delivered internal tooling improvement number {i} for the analytics "
                                      "platform used across several teams" for i in range(30)]
    _, natural = to_pdf(r, a4=True)
    _, fitted = to_pdf(r, a4=True, fit_pages=natural)
    assert natural >= 2 and fitted <= natural


class RepairLLM:
    """Rewrite invents 'Agile'; the fact check flags it; the repair step removes it."""

    def __init__(self):
        self.usage, self.steps = [], []

    def json_call(self, step, system, user):
        self.steps.append(step)
        self.usage.append({"step": step, "model": "fake", "prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0})
        return {
            "rewrite": {"items": [{"id": "E2.2", "action": "rewrite", "reason": "x",
                                   "text": "Fixed bugs in an internal Django dashboard within Agile teams"}],
                        "notes_for_candidate": [{"text": "Prepare to discuss Kubernetes"}]},
            "verify": {"issues": [{"id": "E2.2", "claim": "within Agile teams", "problem": "Agile not in original",
                                   "severity": "medium"}]},
            "repair": {"fixes": [{"id": "E2.2", "text": "Fixed bugs in an internal Django dashboard"}]},
        }[step]


def test_flagged_claims_are_repaired_before_the_user_sees_them():
    llm = RepairLLM()
    v = generate_version(llm, original_text=RESUME_TEXT, resume_json=RESUME_JSON, jd_analysis=JD_ANALYSIS,
                         company="FinNova", job_title="Backend Engineer", settings=Settings())
    assert "Agile" not in resume_to_text(v["resume_json"])
    assert llm.steps == ["rewrite", "verify", "repair"]
    assert v["verification"]["auto_fixed"][0]["claim"] == "within Agile teams"
    assert not v["verification"]["llm_issues"]
    # reverted to the original wording, so it no longer counts as a change
    assert not [c for c in v["change_log"] if c.get("id") == "E2.2"]
    assert v["notes"] == ["Prepare to discuss Kubernetes"]


def test_alternatives_count_as_one_requirement_met_by_any_option():
    from core.ats_scorer import score

    analysis = {"requirement_groups": [
        {"label": "Front-end", "options": ["React", "Angular", "JavaScript"], "required": False},
        {"label": "Back-end", "options": [".NET", "Python"], "required": True},
        {"label": "Orchestration", "options": ["Kubernetes"], "required": True}],
        "keywords": ["React", "PostgreSQL"]}  # React is already covered by its group
    s = score("Built JavaScript apps and Python services on PostgreSQL", analysis)
    assert s["score"] == round(100 * (1 + 2 + 1) / (1 + 2 + 2 + 1))
    assert s["missing"] == ["Kubernetes"]
    assert set(s["alternatives"]) == {"React", "Angular", ".NET"}


def test_unclassified_jd_phrases_are_targets_only_when_mostly_in_the_resume():
    before = {"missing": ["full-stack development", "Agile delivery", "cloud-native applications"],
              "alternatives": ["React"]}
    evidence = [{"term": "React", "status": "absent"}]
    targets = keyword_targets(before, ["React"], evidence, "Built full-stack apps; development in Python")
    assert targets == ["full-stack development (only where it accurately describes the work)"]


class FillerLLM(RepairLLM):
    """Rewrite adds filler to the summary; the rule check flags it and the repair step removes it."""

    def json_call(self, step, system, user):
        if step == "rewrite":
            self.steps.append(step)
            return {"summary": {"text": "Backend engineer utilizing Python with a proven track record of robust APIs.",
                                "reason": "x"}, "items": []}
        if step == "verify":
            self.steps.append(step)
            return {"issues": []}
        if step == "repair":
            self.steps.append(step)
            assert "proven" in user and "utilizing" not in user  # swap happened before the model call
            return {"fixes": [{"id": "SUMMARY", "text": "Backend engineer using Python to build REST APIs."}]}
        raise AssertionError(step)


def test_summary_filler_is_swapped_and_repaired():
    llm = FillerLLM()
    v = generate_version(llm, original_text=RESUME_TEXT, resume_json=RESUME_JSON, jd_analysis=JD_ANALYSIS,
                         company="FinNova", job_title="Backend Engineer", settings=Settings())
    assert v["resume_json"]["summary"] == "Backend engineer using Python to build REST APIs."
    assert llm.steps == ["rewrite", "verify", "repair"]
    assert any("robust" in i["claim"] for i in v["verification"]["auto_fixed"])
    assert not [i for i in v["verification"]["rule_issues"] if "filler" in i["detail"]]


def test_cover_letter_is_found_in_any_response_shape():
    from core.pipeline import _letter_text

    letter = "Dear Hiring Manager,\n\n" + "I built things. " * 20
    assert _letter_text({"cover_letter": letter}) == letter.strip()
    assert _letter_text({"letter": letter}) == letter.strip()
    assert _letter_text({"cover_letter": {"text": letter}}) == letter.strip()
    assert _letter_text({"cover_letter": ["Para one.", "Para two."]}) == "Para one.\n\nPara two."
    assert _letter_text({"anything": letter}) == letter.strip()
    assert _letter_text({}) is None


class CoverFailsLLM(RepairLLM):
    def json_call(self, step, system, user):
        if step == "cover_letter":
            from core.llm_client import LLMError
            raise LLMError("Your Gemini daily quota is used up.", "quota")
        if step == "rewrite":
            return {"items": []}
        return {"issues": []}


def test_cover_letter_failure_keeps_the_resume_and_explains():
    v = generate_version(CoverFailsLLM(), original_text=RESUME_TEXT, resume_json=RESUME_JSON,
                         jd_analysis=JD_ANALYSIS, company="FinNova", job_title="Backend Engineer",
                         settings=Settings(cover_letter=True))
    assert v["cover_letter"] is None and v["resume_json"]["name"] == "Priya Sharma"
    issue = next(i for i in v["verification"]["rule_issues"] if i.get("id") == "COVER_LETTER")
    assert "daily quota" in issue["detail"]


def test_history_retention_and_clear(tmp_path):
    from storage.sqlite_store import SQLiteStore

    store = SQLiteStore(tmp_path / "h.db")
    ids = [store.create_application(company=c, job_title="Dev", jd_text="jd", inputs={}, original_resume_text="r",
                                    resume_json=RESUME_JSON, jd_analysis={}) for c in ("Old", "New")]
    store.add_version(ids[0], {"resume_json": RESUME_JSON, "ats_before": 1, "ats_after": 2})
    store.log_usage([{"step": "rewrite", "model": "m", "prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0}],
                    ids[0], None, "Old")
    with store._conn() as c:  # make the first one 40 days old
        c.execute("UPDATE applications SET created_at = '2000-01-01T00:00:00' WHERE id = ?", (ids[0],))
    assert store.delete_older_than("2020-01-01T00:00:00") == 1
    assert [a["company"] for a in store.list_applications()] == ["New"] and store.get_versions(ids[0]) == []
    assert store.clear_history() == 1 and store.list_applications() == []
    assert len(store.usage_rows()) == 1  # spend history is kept


def test_saved_times_are_utc_and_shown_in_indian_time():
    from storage.sqlite_store import now
    from ui.common import fmt_time

    assert now().endswith("+00:00")  # stored as UTC with its offset
    assert fmt_time("2026-10-14T10:43:59+00:00") == "14 Oct 2026, 04:13 PM IST"
    assert fmt_time("2026-10-14T23:30:00+00:00") == "15 Oct 2026, 05:00 AM IST"  # crosses midnight
    assert fmt_time("not a time") == "not a time"

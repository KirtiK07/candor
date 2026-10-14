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

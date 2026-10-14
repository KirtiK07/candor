import copy

from core.ats_scorer import score
from core.parser import extract_text
from core.pipeline import Settings, generate_version
from core.renderer import resume_to_markdown, resume_to_text, to_docx, to_pdf
from core.tokens import estimate_run, price_for
from core.verifier import check_facts
from storage.sqlite_store import SQLiteStore
from tests.fixtures import JD_ANALYSIS, RESUME_JSON, RESUME_TEXT


class FakeLLM:
    """Stands in for the OpenAI client and returns canned JSON per pipeline step."""

    def __init__(self, tailored):
        self.tailored = tailored
        self.usage = []

    def json_call(self, step, system, user):
        self.usage.append({"step": step, "model": "fake", "prompt_tokens": 100, "completion_tokens": 50, "cost_usd": 0.001})
        return {
            "rewrite": {"summary": {"text": self.tailored["summary"], "reason": "Mirror the JD title"},
                        "items": [{"id": "E1.1", "action": "rewrite", "reason": "JD asks for RESTful APIs",
                                   "text": "Built RESTful APIs in Python (Flask) serving 2 million requests per day"}],
                        "notes_for_candidate": ["Prepare to discuss Kubernetes"]},
            "verify": {"issues": []},
            "cover_letter": {"cover_letter": "Dear Hiring Manager,\n\nHello.\n\nPriya Sharma"},
        }[step]


def test_renderers_produce_all_formats():
    text = resume_to_text(RESUME_JSON)
    assert "PRIYA SHARMA" in text and "• Reduced report generation time by 40%" in text
    # section_order from the original is respected (experience before skills)
    assert text.index("PROFESSIONAL EXPERIENCE") < text.index("SKILLS")
    assert "\\$" not in resume_to_markdown(RESUME_JSON)
    assert to_docx(RESUME_JSON)[:2] == b"PK"
    pdf, pages = to_pdf(RESUME_JSON, a4=False)
    assert pdf.startswith(b"%PDF") and pages == 1


def test_parser_roundtrip_from_generated_docx():
    text = extract_text("resume.docx", to_docx(RESUME_JSON))
    assert "Acme Analytics" in text and "40%" in text


def test_ats_score_improves_with_keywords():
    before = score(RESUME_TEXT, JD_ANALYSIS)
    better = RESUME_TEXT + "\nRESTful microservices with CI/CD pipelines, S3 and Lambda"
    after = score(better, JD_ANALYSIS)
    assert after["score"] > before["score"]
    assert "Kubernetes" in after["missing"]
    assert "Python" in before["matched"]


def test_verifier_flags_fabrications():
    fake = copy.deepcopy(RESUME_JSON)
    fake["experience"][0]["start"] = "Jan 2020"
    fake["experience"][0]["bullets"].append("Cut cloud costs by 65%")
    fake["skills"][0]["items"].append("Kubernetes")
    fake["certifications"].append({"name": "CKA", "issuer": "CNCF", "date": "2024"})
    details = " ".join(i["detail"] for i in check_facts(RESUME_JSON, RESUME_TEXT, "", fake))
    assert "Start date" in details and "'65'" in details and "Kubernetes" in details and "CKA" in details
    assert "has 4 bullets but your original had 3" in details


def test_verifier_clean_on_honest_rewrite():
    honest = copy.deepcopy(RESUME_JSON)
    honest["experience"][0]["bullets"][0] = "Designed RESTful APIs in Python (Flask) handling 2 million requests per day"
    issues = check_facts(RESUME_JSON, RESUME_TEXT, "", honest)
    assert not [i for i in issues if i["severity"] in ("high", "medium")]


def test_verifier_flags_missing_requirements_in_resume_and_letter():
    from core.verifier import check_cover_letter

    claimed = copy.deepcopy(RESUME_JSON)
    claimed["summary"] += " Experienced with CI/CD pipelines."
    forbidden = ["CI/CD pipelines", "Kafka or other message queues"]
    details = " ".join(i["detail"] for i in check_facts(RESUME_JSON, RESUME_TEXT, "", claimed, forbidden))
    assert "CI/CD pipelines" in details and "Kafka" not in details
    letter = "I built Kafka or other message queues based systems and led 5 teams."
    details = " ".join(i["detail"] for i in check_cover_letter(RESUME_JSON, RESUME_TEXT, "", letter, forbidden))
    assert "Cover letter" in details and "Kafka" in details and "'5'" in details


def test_pipeline_and_storage_end_to_end(tmp_path):
    tailored = copy.deepcopy(RESUME_JSON)
    tailored["summary"] = "Backend engineer building RESTful APIs in Python, PostgreSQL and Docker on AWS."
    llm = FakeLLM(tailored)
    s = Settings(include_links=False, include_declaration=True, cover_letter=True, extra_facts="Notice period: 30 days")
    v = generate_version(llm, original_text=RESUME_TEXT, resume_json=RESUME_JSON, jd_analysis=JD_ANALYSIS,
                         company="FinNova", job_title="Backend Engineer", settings=s)
    assert v["resume_json"]["contact"]["linkedin"] == ""
    assert v["resume_json"]["additional_sections"][-1]["title"] == "Declaration"
    assert v["cover_letter"].startswith("Dear Hiring Manager")
    assert v["ats_after"] >= v["ats_before"]

    store = SQLiteStore(tmp_path / "t.db")
    app_id = store.create_application(company="FinNova", job_title="Backend Engineer", jd_text="jd",
                                      inputs=s.to_dict(), original_resume_text=RESUME_TEXT, resume_json=RESUME_JSON,
                                      jd_analysis=JD_ANALYSIS, photo=b"img")
    v1 = store.add_version(app_id, {**v, "model": "fake", "prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0.01})
    v2 = store.add_version(app_id, {**v, "model": "fake", "prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0.01})
    store.set_final(app_id, v2)
    store.log_usage(llm.usage, app_id, v2, "FinNova")
    versions = store.get_versions(app_id)
    assert [x["version_no"] for x in versions] == [1, 2] and versions[1]["is_final"] and not versions[0]["is_final"]
    assert store.get_application(app_id)["photo"] == b"img"
    row = store.list_applications()[0]
    assert row["versions"] == 2 and row["final_version"] == 2
    store.delete_application(app_id)
    assert store.list_applications() == [] and len(store.usage_rows()) == 3  # usage survives delete
    assert v1


def test_pricing_prefix_and_estimate():
    p, exact = price_for("gpt-4o-mini-2024-07-18")
    assert p["input"] == 0.15 and not exact
    est = estimate_run(RESUME_TEXT, "jd " * 300, "gpt-4.1-mini", cover_letter=True)
    assert est["input"] > 0 and est["cost"] > 0

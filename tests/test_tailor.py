import copy

from core.renderer import resume_to_text
from core.tailor import apply_plan, change_report, itemize, keyword_targets, min_rewrites, plan_stats
from tests.fixtures import RESUME_JSON

RESUME = copy.deepcopy(RESUME_JSON)
RESUME["projects"] = [
    {"name": "Expense Tracker API", "role": "", "dates": "2022", "link": "", "tech": ["Flask"],
     "bullets": ["Built a REST API with JWT auth", "Deployed it with Docker on EC2"]},
    {"name": "Log Analyzer", "role": "", "dates": "2021", "link": "", "tech": ["Python"],
     "bullets": ["Wrote a CLI that parses Nginx logs"]},
]


def test_itemize_assigns_stable_ids():
    text, items = itemize(RESUME)
    assert {"E1.1", "E1.3", "E2.2", "P1.2", "P2.1"} <= set(items)
    assert items["P1.1"] == ("Project · Expense Tracker API", "Built a REST API with JWT auth")
    assert "E1: Software Engineer at Acme Analytics (Jul 2022 – Present)" in text


def test_apply_plan_locks_facts_and_explains_every_change():
    plan = {
        "summary": {"text": "Backend Engineer building RESTful APIs in Python.", "reason": "Mirror JD title",
                    "keywords": ["RESTful APIs"]},
        "items": [
            {"id": "E1.2", "action": "rewrite", "text": "Optimized PostgreSQL queries, cutting report time by 40%",
             "reason": "JD stresses query optimization", "keywords": ["query optimization"]},
            {"id": "E1.1", "action": "keep"},
            {"id": "E1.3", "action": "keep"},
            {"id": "P2.1", "action": "remove", "reason": "Not relevant to payments"},
        ],
        "project_order": {"order": ["P2", "P1"], "reason": "test"},
        # a model trying to change facts has no way to: there is no field for them
        "experience": [{"company": "Google", "title": "CTO"}],
    }
    new, changes = apply_plan(RESUME, plan, page_limit=1)
    assert [e["company"] for e in new["experience"]] == ["Acme Analytics", "BrightSoft Solutions"]
    assert new["experience"][0]["start"] == "Jul 2022" and new["experience"][0]["title"] == "Software Engineer"
    # E1.2 moved first, rewritten, with its reason
    assert new["experience"][0]["bullets"][0].startswith("Optimized PostgreSQL")
    rewrite = next(c for c in changes if c["type"] == "rewrite" and c["section"].startswith("Experience"))
    assert rewrite["reason"] == "JD stresses query optimization" and rewrite["before"].startswith("Reduced report")
    # the resume is far under one page, so the removed project bullet is restored and explained
    assert "Wrote a CLI that parses Nginx logs" in resume_to_text(new)
    assert any(c["type"] == "kept" and "fits within" in c["reason"] for c in changes)
    assert [p["name"] for p in new["projects"]] == ["Log Analyzer", "Expense Tracker API"]
    assert all(c["reason"] for c in changes)


def test_removal_sticks_when_over_page_budget():
    big = copy.deepcopy(RESUME)
    big["achievements"] = ["word " * 650]  # pushes the resume over one page
    plan = {"items": [{"id": "P2.1", "action": "remove", "reason": "Irrelevant to the JD"}]}
    new, changes = apply_plan(big, plan, page_limit=1)
    assert new["projects"][1]["bullets"] == [] and new["projects"][1]["name"] == "Log Analyzer"  # project kept
    removed = [c for c in changes if c["type"] == "remove"]
    assert removed and removed[0]["reason"] == "Irrelevant to the JD"
    report = change_report(changes, plan_stats(changes, len(itemize(big)[1])))
    assert "REMOVED" in report and "Irrelevant to the JD" in report


def test_bad_ids_and_actions_are_ignored():
    plan = {"items": [{"id": "E9.9", "action": "rewrite", "text": "Invented"}, {"id": "e1.1", "action": "rewrite",
                                                                                "text": "Built RESTful APIs in Flask"}]}
    new, _ = apply_plan(RESUME, plan, page_limit=1)
    assert "Invented" not in resume_to_text(new)
    assert new["experience"][0]["bullets"][0] == "Built RESTful APIs in Flask"


def test_added_outcome_clauses_are_flagged():
    from core.verifier import check_added_outcomes

    changes = [
        {"type": "rewrite", "section": "Experience · X", "before": "Assisted in migrating services to Docker",
         "after": "Supported migration of services to Docker, improving deployment consistency and portability."},
        {"type": "rewrite", "section": "Experience · Y", "before": "Cut costs, improving margins by 5%",
         "after": "Reduced costs, improving margins by 5%"},  # result was in the original: fine
    ]
    issues = check_added_outcomes(changes)
    assert len(issues) == 1 and "improving deployment consistency" in issues[0]["detail"]


def test_punctuation_only_change_is_not_a_rewrite():
    plan = {"items": [{"id": "E1.3", "action": "rewrite", "reason": "x",
                       "text": "Assisted in migrating services to Docker containers on AWS EC2."}]}
    new, changes = apply_plan(RESUME, plan, page_limit=1)
    assert "Assisted in migrating services to Docker containers on AWS EC2" in new["experience"][0]["bullets"]
    assert not [c for c in changes if c["type"] == "rewrite"]


def test_skill_rename_is_not_a_removal():
    plan = {"skills": {"groups": [{"category": "Cloud", "items": ["AWS (EC2)", "Docker"]},
                                  {"category": "Core", "items": ["Python", "Flask", "Django", "PostgreSQL", "Git",
                                                                 "Linux"]}], "reason": "Grouped"}}
    _, changes = apply_plan(RESUME, plan, page_limit=1)
    assert not [c for c in changes if c["type"] == "remove"]


def test_targets_and_minimums():
    assert keyword_targets({"missing": ["FastAPI", "Kubernetes", "microservices"]}, ["Kubernetes"]) == ["FastAPI", "microservices"]
    assert min_rewrites("Moderate", 10, {"Moderate": 0.7}) == 7
    assert min_rewrites("Strong", 10, {"Strong": 1.0}) == 10

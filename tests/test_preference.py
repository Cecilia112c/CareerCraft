from agents.core.schemas import ProfileData, ScoredJob
from agents.jd_agent import JobGoal, score_job
from agents.jd_agent.salary import parse_salary


def test_parse_salary():
    assert parse_salary("15-25K·14薪") == (15, 25)
    assert parse_salary("15K-25K") == (15, 25)
    assert parse_salary("1.5-2万") == (15, 20)
    assert parse_salary("8000-12000元/月") == (8, 12)
    lo, hi = parse_salary("200-300元/天")
    assert 4.2 < lo < 4.5 and 6.4 < hi < 6.6          # 按每月 21.75 个工作日换算
    assert parse_salary("200-300/天")[0] < 5          # 日薪没写单位按元
    assert parse_salary("30-40万/年") == (25, 33.3)
    assert parse_salary("20K") == (20, 20)
    assert parse_salary("薪资面议") is None
    assert parse_salary("") is None


PROFILE = ProfileData.model_validate({"skills": ["Go", "Redis", "MySQL"]})


def job(**kw):
    base = {"title": "后端开发工程师", "company": "某科技", "city": "深圳", "salary": "15-25K",
            "keywords": ["Go", "Redis", "Kafka"]}
    return ScoredJob(**(base | kw))


def test_preference_match():
    goal = JobGoal(titles=["后端开发"], cities=["深圳"], salary_min=15, salary_max=30)
    j = score_job(job(), PROFILE, goal)
    assert j.pref_match and j.salary_low == 15 and j.salary_high == 25
    assert any("城市符合" in n for n in j.pref_notes) and any("薪资符合" in n for n in j.pref_notes)


def test_preference_city_mismatch():
    goal = JobGoal(titles=["后端开发"], cities=["深圳"])
    j = score_job(job(city="北京"), PROFILE, goal)
    assert not j.pref_match


def test_preference_salary_too_low():
    goal = JobGoal(titles=["后端开发"], salary_min=30)
    j = score_job(job(salary="15-25K"), PROFILE, goal)
    assert not j.pref_match and any("薪资不符" in n for n in j.pref_notes)


def test_unknown_info_is_not_rejected():
    goal = JobGoal(titles=["后端开发"], cities=["深圳"], salary_min=15)
    j = score_job(job(city="", salary="面议"), PROFILE, goal)
    assert j.pref_match and "城市未知" in j.pref_notes


def test_score_prefers_matching_jobs():
    goal = JobGoal(titles=["后端开发"], cities=["深圳"], salary_min=15)
    good = score_job(job(), PROFILE, goal).score
    bad = score_job(job(city="北京", salary="5-8K"), PROFILE, goal).score
    assert good > bad

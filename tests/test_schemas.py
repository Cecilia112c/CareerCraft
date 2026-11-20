from agents.core.schemas import (
    ProfileData, ResumeDoc, doc_to_text, get_text, iter_items, set_text,
)

PROFILE = {
    "basic": {"name": "张三", "phone": "13800000000", "summary": "后端开发方向"},
    "education": [{"id": "e1", "school": "某大学", "major": "计算机", "bullets": ["GPA 3.8/4.0"]}],
    "experience": [{
        "id": "x1", "company": "某科技", "title": "后端实习生", "dates": "2024.06-2024.09",
        "projects": [{"id": "p1", "name": "订单服务优化",
                      "background": [{"id": "b1", "text": "订单接口高峰期延迟高"}],
                      "responsibilities": ["设计 Redis 缓存"],          # 字符串也能被接受
                      "impact": None, "keywords": "Go, Redis"}],
    }],
    "skills": "Python、Go",
}


def test_coercion_from_llm_shapes():
    p = ProfileData.model_validate(PROFILE)
    proj = p.experience[0].projects[0]
    assert proj.responsibilities[0].text == "设计 Redis 缓存" and proj.responsibilities[0].id
    assert proj.impact == []
    assert proj.keywords == ["Go", "Redis"]
    assert p.skills == ["Python", "Go"]
    assert p.education[0].bullets[0].text == "GPA 3.8/4.0"


def test_get_set_text_by_key():
    p = ProfileData.model_validate(PROFILE)
    assert get_text(p, "b1") == "订单接口高峰期延迟高"
    assert set_text(p, "b1", "新的背景")
    assert get_text(p, "b1") == "新的背景"
    assert set_text(p, "x1.company", "新公司") and p.experience[0].company == "新公司"
    assert set_text(p, "p1.keywords", "Go / Kafka") and p.experience[0].projects[0].keywords == ["Go", "Kafka"]
    assert set_text(p, "basic.summary", "简介")
    assert not set_text(p, "x1.unknown_field", "x")     # 白名单之外
    assert not set_text(p, "nope", "x")


def test_iter_items_and_text():
    doc = ResumeDoc.model_validate(PROFILE)
    ids = [r.id for r in iter_items(doc)]
    assert "b1" in ids and "basic.summary" in ids
    doc.presentation.hidden_ids = ["p1"]
    text = doc_to_text(doc)
    assert "订单服务优化" not in text and "某科技" in text

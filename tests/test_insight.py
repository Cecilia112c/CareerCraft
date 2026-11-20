from agents.jd_agent.insight import aggregate, canonical, extract_terms


def test_alias_normalization():
    terms = extract_terms("熟悉 Golang / k8s，了解 springboot 和大语言模型应用开发，会用 Vue3")
    assert {"Go", "Kubernetes", "Spring", "大模型", "Vue"} <= terms
    assert canonical("golang") == "Go" and canonical("K8S") == "Kubernetes"


def test_short_aliases_are_case_sensitive():
    assert "Go" not in extract_terms("let's go to Google")
    assert "Go" in extract_terms("使用Go语言开发")
    assert "Elasticsearch" not in extract_terms("支持 ES6 语法")
    assert "C++" in extract_terms("精通 C++ 与 STL")


def test_extra_keywords_from_llm_kept_or_normalized():
    terms = extract_terms("", ["golang", "推荐系统", "这是一个很长很长的句子不应该成为关键词。"])
    assert "Go" in terms and "推荐系统" in terms and len(terms) == 2


def test_aggregate_document_frequency_and_coverage():
    docs = [(1, {"Python", "MySQL", "沟通能力"}), (2, {"Python", "Kafka"}), (3, {"Python", "Kafka", "Redis"})]
    out = aggregate(docs, {"python", "Redis"})
    top = {t.term: t for t in out.terms}
    assert top["Python"].count == 3 and top["Python"].ratio == 1.0 and top["Python"].have
    assert top["Kafka"].doc_ids == [2, 3] and not top["Kafka"].have
    assert out.terms[0].term == "Python"
    assert "Kafka" in out.missing_top and "沟通能力" not in out.missing_top   # 通用素质不计入建议
    assert 0 < out.coverage < 1

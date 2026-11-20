from agents.resume_agent.grounding import verify_grounded


def test_grounding_uses_only_referenced_l1_evidence():
    facts = {
        "profile:1": {"statement": "开发 Python 接口，P99 为 350ms", "level": "L1"},
        "claim:2": {"statement": "使用 Kafka 处理消息", "level": "L1"},
        "claim:3": {"statement": "吞吐达到 10000 QPS", "level": "L2"},
    }
    assert verify_grounded("使用 Python 开发接口", ["profile:1"], facts) == []
    assert verify_grounded("使用 Kafka 处理消息", ["profile:1"], facts)
    assert verify_grounded("吞吐达到 10000 QPS", ["claim:3"], facts)
    assert verify_grounded("使用 Kafka 处理消息", ["claim:2"], facts) == []
    assert verify_grounded("使用 Kafka 处理消息", [], facts)

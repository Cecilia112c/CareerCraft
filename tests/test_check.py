from agents.resume_agent.check import check_text

REF = "负责订单服务开发，使用 Go 和 Redis，将接口 P99 从 2.1s 降到 350ms，覆盖 3 个业务线"


def test_rewording_is_ok():
    assert check_text("基于 Go 与 Redis 重构订单服务，P99 由 2.1s 降至 350ms", REF) == []


def test_new_number_is_rejected():
    problems = check_text("P99 降低 80%", REF)
    assert problems and "80" in problems[0]


def test_new_tech_is_rejected():
    problems = check_text("使用 Kafka 解耦订单服务", REF)
    assert problems and "kafka" in problems[0]


def test_empty_is_rejected():
    assert check_text("  ", REF)

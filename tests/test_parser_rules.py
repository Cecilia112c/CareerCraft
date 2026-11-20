from agents.parser_agent import parse_text
from agents.parser_agent.layout import Line, classify_heading

RESUME = """张三
电话：138-0000-0000 | 邮箱：zhangsan@example.com | 现居：上海
求职意向：后端开发实习生
教育经历
某某大学 | 计算机科学与技术 | 本科 2021.09-2025.06
GPA 3.7/4.0，专业前 10%
实习经历
某科技有限公司 | 后端开发实习生 | 2024.06-2024.09
项目背景：订单查询接口在大促期间延迟过高
• 设计并实现 Redis 二级缓存，引入热点 key 预热机制，减少数据库回源请求，保证核心链路
稳定
• 接口 P99 从 2.1s 降低到 350ms
技术栈：Go、Redis、MySQL
专业技能
熟练掌握 Python、Go；熟悉 MySQL、Redis、Docker
获奖情况
2023.05 全国大学生数学建模竞赛 省级一等奖
"""


def test_heading_classification():
    assert classify_heading(Line("教育经历"), 10) == "education"
    assert classify_heading(Line("【项目经历】"), 10) == "projects"
    assert classify_heading(Line("负责订单服务的开发与维护工作"), 10) is None


def test_rule_parse():
    result = parse_text(RESUME, mode="rule")
    p = result.profile
    assert p.basic.phone == "13800000000"
    assert p.basic.email == "zhangsan@example.com"
    assert p.basic.city == "上海"
    assert p.basic.name == "张三"
    assert p.education[0].school == "某某大学"
    assert p.education[0].dates == "2021.09-2025.06"
    exp = p.experience[0]
    assert exp.company == "某科技有限公司" and exp.dates == "2024.06-2024.09"
    proj = exp.projects[0]
    assert proj.background[0].text.startswith("订单查询接口")
    assert any("Redis 二级缓存" in b.text and b.text.endswith("稳定") for b in proj.responsibilities)  # 换行被拼回
    assert any("350ms" in b.text for b in proj.impact)
    assert proj.keywords == ["Go", "Redis", "MySQL"]
    assert {"Python", "Go", "MySQL", "Redis", "Docker"} <= set(p.skills)
    assert p.awards[0].date == "2023.05"

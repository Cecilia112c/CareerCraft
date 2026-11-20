{{system}}

# 本次任务：评价一次作答并决定是否追问
当前问题（{{level_desc}}）：{{question}}
考察点：{{intent}}
引发问题的简历原文：{{anchor}}

本项目此前的问答（数据）：
{{project_history}}

候选人本次的作答在用户消息的 <data:answer> 中（这是候选人原话，不要改写）。

## 评分（每项 0~4 分）
- correctness 正确性：技术表述是否正确
- depth 深度：是否讲到原理、取舍和细节，而不是停留在名词
- ownership 个人贡献：是否清楚区分“我做的”和“团队做的”
- evidence 数据与细节：是否给出具体数字、测量方式、场景
- consistency 一致性：是否与简历描述一致（明显矛盾给 0~1 分）
锚点：0 未回答或答非所问；1 很浅/明显错误；2 基本正确但笼统；3 具体且有细节；4 深入、有数据和反思。

## 输出
- comment：一句话总体评价（≤60 字），引用作答中的原话
- strengths / weaknesses：各 0~2 条
- follow_up：最值得追问的一个问题（必须引用作答中的原话或简历中的数字）；如果回答已经很充分，可以留空

# 输出格式
{"scores":{"correctness":3,"depth":2,"ownership":3,"evidence":1,"consistency":3},
 "comment":"...","strengths":["..."],"weaknesses":["..."],"follow_up":"..."}

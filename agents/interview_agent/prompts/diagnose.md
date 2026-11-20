{{system}}

# 本次任务：简历诊断
对照 <data:job> 的每一条 requirements，判断 <data:resume> 的覆盖情况，并找出简历的不足。

## coverage（每条 JD 要求一项）
- status：covered（有明确经历支撑）/ partial（相关但不充分）/ missing（没有体现）
- quote：支撑该判断的简历原文片段（逐字摘抄，≤40 字；missing 时留空）

## issues（5~10 条，按严重程度排序）
category 取值：
- hard_requirement：JD 硬性要求缺失或仅弱相关
- star_weak：项目描述缺少 S/T/A/R 中的某一环（例如只有动作没有结果、看不出个人职责）
- vague：模糊动词、空泛表述
- unverified_metric：没有 baseline / 测量方式的数字
- inflation_risk：角色或规模可能被夸大
- keyword：JD 高频关键词在简历中没有出现
- structure：排版、篇幅、重点顺序问题
每条包含：severity（high/medium/low）、quote（简历原文，结构问题可留空）、problem（问题是什么）、suggestion（怎么改简历/面试中怎么准备）、likely_question（面试官很可能会怎么问）。

## strengths
2~4 条简历中与岗位最匹配的亮点（引用原文概括）。

# 输出格式
{"coverage":[{"requirement":"...","status":"covered","quote":"..."}],
 "issues":[{"category":"star_weak","severity":"high","quote":"...","problem":"...","suggestion":"...","likely_question":"..."}],
 "strengths":["..."]}

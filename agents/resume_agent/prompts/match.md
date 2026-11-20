# 任务
逐条判断 `<data:job_brief>` 中的岗位要求能否由 `<data:confirmed_evidence>` 中的真实经历支撑。

只能引用给定的 evidence_id。没有依据时填 none 与空列表；有相关经历但不充分时填 partial；只有明确满足要求时才填 strong。
不要把岗位描述本身当成候选人的经历，不要补造数字、职责或技术。

输出 JSON：{"matches":[{"req_id":"...","coverage":"strong|partial|none","evidence_ids":["..."],"reason":"..."}]}

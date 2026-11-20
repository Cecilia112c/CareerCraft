export function splitJD(description: string): { responsibilities: string[]; requirements: string[] } {
  const lines = description.split(/\n+/).map((x) => x.trim()).filter(Boolean)
  const duties: string[] = [], requirements: string[] = []
  let section: 'duties' | 'requirements' | '' = ''
  for (const line of lines) {
    if (/^(职位要求|任职要求|任职资格|岗位要求|任职条件)[：:]?$/.test(line)) { section = 'requirements'; continue }
    if (/^(职位描述|岗位职责|工作内容|工作职责)[：:]?$/.test(line)) { section = 'duties'; continue }
    const value = line.replace(/^(?:\d+[.、]|[•·])\s*/, '').trim()
    if (value.length < 4) continue
    if (section === 'duties') duties.push(value)
    if (section === 'requirements') requirements.push(value)
  }
  return { responsibilities: duties, requirements }
}

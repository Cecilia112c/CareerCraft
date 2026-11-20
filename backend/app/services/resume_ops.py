"""Pure-code resume operations: versions, patches, sync-back to profile."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from agents.core.schemas import (
    ProfileData, ResumeDoc, TextItem, find_project, get_text, iter_items, iter_projects, set_text,
)
from backend.app.models import Profile, Resume, ResumeVersion


def get_version(session: Session, resume: Resume, version: int | None = None) -> ResumeVersion:
    v = version or resume.current_version
    row = session.exec(select(ResumeVersion).where(ResumeVersion.resume_id == resume.id,
                                                  ResumeVersion.version == v)).first()
    if row is None:
        raise HTTPException(404, "该版本不存在（简历可能仍在生成中）")
    return row


def add_version(session: Session, resume: Resume, doc: ResumeDoc, note: str,
                base_version: int | None = None) -> ResumeVersion:
    if base_version is not None and base_version != resume.current_version:
        raise HTTPException(409, f"简历已被更新到 v{resume.current_version}，请刷新后再操作")
    resume.current_version += 1
    resume.updated_at = datetime.now(timezone.utc)
    row = ResumeVersion(resume_id=resume.id, version=resume.current_version,
                        data=doc.model_dump(mode="json"), note=note)
    session.add(resume)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def apply_patches(doc: ResumeDoc, patches: list[dict]) -> int:
    applied = 0
    for patch in patches:
        if set_text(doc, str(patch.get("id", "")), str(patch.get("new", ""))):
            applied += 1
    return applied


# ---------------------------------------------------------------- sync back

_FIELDS = ("background", "responsibilities", "impact")
_FIELD_LABEL = {"background": "背景", "responsibilities": "职责", "impact": "成果"}


def sync_diff(resume: ResumeDoc, profile: ProfileData) -> list[dict]:
    """Differences the user may copy back into the profile. Identity fields are never included."""
    diffs: list[dict] = []
    profile_ids = set()
    for ref in iter_items(profile):
        profile_ids.add(ref.id)
        new = get_text(resume, ref.id)
        if new and new.strip() != (ref.text or "").strip():
            diffs.append({"key": ref.id, "kind": "replace", "context": ref.context,
                          "old": ref.text, "new": new})
    for project, ctx in iter_projects(resume):
        found = find_project(profile, project.id)
        if not found:
            continue
        for field in _FIELDS:
            for item in getattr(project, field):
                if item.id not in profile_ids and item.text.strip():
                    diffs.append({"key": f"add:{project.id}:{field}:{item.id}", "kind": "add",
                                  "context": f"{ctx}｜新增{_FIELD_LABEL[field]}", "old": "", "new": item.text})
        old_kw, new_kw = found[0].keywords, project.keywords
        if new_kw and new_kw != old_kw:
            diffs.append({"key": f"{project.id}.keywords", "kind": "replace", "context": f"{ctx}｜技术关键词",
                          "old": " / ".join(old_kw), "new": " / ".join(new_kw)})
    return diffs


def apply_sync(resume: ResumeDoc, profile: ProfileData, keys: list[str]) -> int:
    diffs = {d["key"]: d for d in sync_diff(resume, profile)}
    applied = 0
    for key in keys:
        diff = diffs.get(key)
        if diff is None:
            continue
        if diff["kind"] == "add":
            _, project_id, field, item_id = key.split(":", 3)
            found = find_project(profile, project_id)
            if found:
                getattr(found[0], field).append(TextItem(id=item_id, text=diff["new"]))
                applied += 1
        elif set_text(profile, key, diff["new"]):
            applied += 1
    return applied


def save_profile(session: Session, user_id: int, profile: ProfileData) -> Profile:
    row = session.exec(select(Profile).where(Profile.user_id == user_id)).first()
    if row is None:
        row = Profile(user_id=user_id)
    row.data = profile.model_dump(mode="json")
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row

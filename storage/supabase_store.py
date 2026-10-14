"""Supabase (hosted Postgres) store with the same interface as SQLiteStore.

Use this when deploying to Streamlit Community Cloud, whose disk is wiped on restart.
Create the tables first by running storage/supabase_schema.sql in the Supabase SQL editor.
"""
import base64

from storage.sqlite_store import VERSION_COLS, now


def _photo_out(row: dict) -> dict:
    if row.get("photo"):
        row["photo"] = base64.b64decode(row["photo"])
    return row


class SupabaseStore:
    name = "Supabase (cloud Postgres)"

    def __init__(self, url: str, key: str):
        from supabase import create_client

        # The dashboard shows the REST endpoint (".../rest/v1/"); the client wants the bare project URL.
        url = str(url or "").strip().rstrip("/").removesuffix("/rest/v1")
        self.db = create_client(url, str(key or "").strip())

    def create_application(self, *, company, job_title, jd_text, inputs, original_resume_text,
                           resume_json, jd_analysis, photo=None) -> int:
        row = dict(created_at=now(), company=company, job_title=job_title, jd_text=jd_text, inputs=inputs,
                   original_resume_text=original_resume_text, resume_json=resume_json, jd_analysis=jd_analysis,
                   photo=base64.b64encode(photo).decode() if photo else None)
        return self.db.table("applications").insert(row).execute().data[0]["id"]

    def add_version(self, app_id: int, data: dict) -> int:
        last = (self.db.table("versions").select("version_no").eq("application_id", app_id)
                .order("version_no", desc=True).limit(1).execute().data)
        row = {"application_id": app_id, "version_no": (last[0]["version_no"] if last else 0) + 1,
               "created_at": now(), **{k: data.get(k) for k in VERSION_COLS}}
        return self.db.table("versions").insert(row).execute().data[0]["id"]

    def get_application(self, app_id: int) -> dict | None:
        data = self.db.table("applications").select("*").eq("id", app_id).execute().data
        return _photo_out(data[0]) if data else None

    def get_versions(self, app_id: int) -> list[dict]:
        return (self.db.table("versions").select("*").eq("application_id", app_id)
                .order("version_no").execute().data)

    def list_applications(self) -> list[dict]:
        apps = (self.db.table("applications").select("id, created_at, company, job_title")
                .order("id", desc=True).execute().data)
        vers = (self.db.table("versions").select("application_id, version_no, ats_after, cost_usd, is_final")
                .execute().data)
        for a in apps:
            vs = [v for v in vers if v["application_id"] == a["id"]]
            a["versions"] = len(vs)
            a["best_ats"] = max((v["ats_after"] or 0 for v in vs), default=None)
            a["cost_usd"] = sum(v["cost_usd"] or 0 for v in vs)
            a["final_version"] = next((v["version_no"] for v in vs if v["is_final"]), None)
        return apps

    def set_final(self, app_id: int, version_id: int) -> None:
        self.db.table("versions").update({"is_final": False}).eq("application_id", app_id).execute()
        self.db.table("versions").update({"is_final": True}).eq("id", version_id).execute()

    def delete_application(self, app_id: int) -> None:
        self.db.table("applications").delete().eq("id", app_id).execute()

    def log_usage(self, entries: list[dict], app_id=None, version_id=None, company=None) -> None:
        if entries:
            self.db.table("usage_log").insert([
                {"application_id": app_id, "version_id": version_id, "company": company, "ts": now(), **e}
                for e in entries
            ]).execute()

    def usage_rows(self) -> list[dict]:
        return self.db.table("usage_log").select("*").order("id").execute().data

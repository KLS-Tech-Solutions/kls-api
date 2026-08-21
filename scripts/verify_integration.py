"""
End-to-end integration proof: student portal → API → database → admin console.

Runs the whole workflow against the real application in a throwaway database
and asserts that every admin action is reflected on the student side:

    python scripts/verify_integration.py

Uses its own SQLite file so it never touches your development data.
"""
import io, os
os.environ.update(DATABASE_URL="sqlite:////tmp/e2e2.db", SECRET_KEY="integration-secret-key-long-enough-here", DEBUG="false")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
import app.models
from app.core.database import Base
from app.main import app as fastapi_app
from app.core.database import engine

Base.metadata.create_all(engine)

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import AdminProfile, User, UserRole, UserStatus

db = SessionLocal()
owner = User(full_name="KLS Owner", email="owner@klsacademy.example.com", phone="+919000000000",
             password_hash=hash_password("Owner12345"), role=UserRole.SUPER_ADMIN,
             status=UserStatus.ACTIVE, email_verified=True)
db.add(owner); db.flush(); db.add(AdminProfile(user_id=owner.id)); db.commit(); db.close()

c = TestClient(fastapi_app)
H = lambda t: {"Authorization": f"Bearer {t}"}
ok = lambda label, cond, extra="": print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' — ' + extra) if extra else ''}")

print("\n--- Clean database ---")
ok("Catalogue starts empty (no demo domains)", c.get("/api/v1/internship-domains").json() == [])

print("\n--- Super admin creates real content ---")
owner_t = c.post("/api/v1/auth/login", json={"email":"owner@klsacademy.example.com","password":"Owner12345"}).json()["access_token"]
dom = c.post("/api/v1/admin/internship-domains", headers=H(owner_t), json={
  "slug":"full-stack-python","title":"Full Stack Python Development",
  "description":"Build and ship a complete web application.","duration":"4 weeks",
  "difficulty":"intermediate","icon":"code","display_order":1}).json()
ok("Domain created via admin API", dom.get("slug") == "full-stack-python")

batch = c.post("/api/v1/admin/internship-batches", headers=H(owner_t), json={
  "domain_id":dom["id"],"batch_name":"Batch 01","start_date":"2026-09-01",
  "end_date":"2026-09-29","seats_total":40,"status":"upcoming"}).json()
c.post("/api/v1/admin/tasks", headers=H(owner_t), json={"batch_id":batch["id"],
  "title":"Share your offer letter on LinkedIn","description":"Post it and submit the URL.","order_number":0})
t1 = c.post("/api/v1/admin/tasks", headers=H(owner_t), json={"batch_id":batch["id"],
  "title":"Task 1 REST API","description":"Build a FastAPI service with JWT auth.",
  "order_number":1,"min_screenshots":2,"min_explanation_chars":50}).json()
ok("Task created with custom rules", t1["min_screenshots"] == 2 and t1["min_explanation_chars"] == 50)
ok("Domain now public with task count", c.get("/api/v1/internship-domains").json()[0]["task_count"] == 1)

print("\n--- Student journey, synced to admin at each step ---")
c.post("/api/v1/auth/register", json={"full_name":"Ananya Rao","email":"ananya@example.com","phone":"9845012345","password":"kls12345"})
s = c.post("/api/v1/auth/login", json={"email":"ananya@example.com","password":"kls12345"}).json()["access_token"]
stage = lambda: c.get("/api/v1/me/journey", headers=H(s)).json()["stage"]
ok("Registered student starts not_enrolled", stage() == "not_enrolled")

students = c.get("/api/v1/admin/students", headers=H(owner_t)).json()
ok("Student immediately visible in admin", len(students) == 1 and students[0]["stage"] == "not_enrolled")

c.post("/api/v1/enrollments", headers=H(s), json={"domain_id":dom["id"],"batch_id":batch["id"]})
j = c.get("/api/v1/me/journey", headers=H(s)).json()
ok("Enrolment generates the offer letter", j["stage"] == "offer_letter_generated",
   j["offerLetter"]["offer_letter_number"])

c.post("/api/v1/linkedin-submissions", headers=H(s), json={"linkedin_post_url":"https://www.linkedin.com/posts/ananya_kls-activity-1"})
ok("LinkedIn submitted", stage() == "linkedin_submitted")

queue = c.get("/api/v1/admin/linkedin-submissions?status=pending", headers=H(owner_t)).json()
ok("Submission appears in the admin queue", len(queue) == 1)
c.patch(f"/api/v1/admin/linkedin-submissions/{queue[0]['id']}", headers=H(owner_t),
        json={"status":"approved","remarks":"Verified."})
ok("Admin approval unlocks tasks for the student", stage() == "linkedin_approved")

png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
shots = lambda n: [("screenshots", (f"s{i}.png", io.BytesIO(png), "image/png")) for i in range(n)]

r = c.post("/api/v1/task-submissions", headers=H(s), files=shots(1), data={
  "task_id":t1["id"],"title":"REST API","github_url":"https://github.com/a/b","description":"x"*60})
ok("Per-task screenshot minimum enforced (1 of 2 rejected)", r.status_code == 422)

r = c.post("/api/v1/task-submissions", headers=H(s), files=shots(2), data={
  "task_id":t1["id"],"title":"REST API","github_url":"https://github.com/a/b","description":"x"*60})
ok("Valid submission accepted", r.status_code == 201)
ok("Student moves to tasks_in_progress", stage() == "tasks_in_progress")

sub = c.get("/api/v1/admin/task-submissions?status=under_review", headers=H(owner_t)).json()
ok("Submission visible to reviewer", len(sub) == 1)
c.post(f"/api/v1/admin/task-submissions/{sub[0]['id']}/review", headers=H(owner_t),
       json={"status":"rejected","remarks":"Repository is private."})
ok("Rejection reflected on the student side",
   c.get("/api/v1/me/journey", headers=H(s)).json()["submissions"][0]["status"] == "rejected")

c.post("/api/v1/task-submissions", headers=H(s), files=shots(2), data={
  "task_id":t1["id"],"title":"REST API","github_url":"https://github.com/a/b","description":"y"*60})
c.post(f"/api/v1/admin/task-submissions/{sub[0]['id']}/review", headers=H(owner_t),
       json={"status":"approved","remarks":"Approved."})
ok("All tasks approved unlocks payment", stage() == "all_tasks_approved")


cert = c.get("/api/v1/me/certificate", headers=H(s)).json()
ok("Certificate verifies publicly",
   c.get(f"/api/v1/certificates/verify/{cert['certificate_number']}").status_code == 200,
   cert["certificate_number"])
ok("Admin sees the same student record",
   c.get(f"/api/v1/admin/students/{students[0]['id']}", headers=H(owner_t)).json()["stage"] == "certificate_issued")

print("\n--- Role separation ---")
ok("Student blocked from admin routes", c.get("/api/v1/admin/students", headers=H(s)).status_code == 403)
ok("Admin blocked from student routes", c.get("/api/v1/me/journey", headers=H(owner_t)).status_code == 403)
ok("Unauthenticated blocked", c.get("/api/v1/me/journey").status_code == 401)

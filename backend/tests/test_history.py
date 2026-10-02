# Print history: job tracking from printer readings, and Klipper history import.
import history

T0 = 1_800_000_000.0   # fixed clock for predictable durations


def reading(pid, state, job="part.gcode", progress=0.0, connected=True, raw=None, **extra):
    return {"id": pid, "name": f"Printer {pid}", "state": state, "raw_state": raw or state, "job": job,
            "progress": progress, "connected": connected, **extra}


def job_rows(pid):
    c = history._db()
    rows = [dict(r) for r in c.execute("SELECT * FROM print_jobs WHERE printer_id=? ORDER BY id", (pid,))]
    c.close()
    return rows


def test_completed_print(client):
    history.observe(reading(501, "printing", progress=10), now=T0)
    history.observe(reading(501, "printing", progress=60), now=T0 + 600)
    history.observe(reading(501, "complete", progress=100), now=T0 + 3600)
    [j] = job_rows(501)
    assert j["status"] == "completed" and j["ended_at"] - j["started_at"] == 3600 and j["progress"] == 100


def test_cancelled_and_failed_prints(client):
    history.observe(reading(502, "printing", progress=20), now=T0)
    history.observe(reading(502, "idle", job=None, progress=0), now=T0 + 100)
    history.observe(reading(503, "printing", progress=20), now=T0)
    history.observe(reading(503, "error", progress=20), now=T0 + 100)
    assert job_rows(502)[0]["status"] == "cancelled"
    assert job_rows(503)[0]["status"] == "failed"


def test_offline_keeps_job_open(client):
    history.observe(reading(504, "printing", progress=30), now=T0)
    history.observe(reading(504, "offline", job=None, connected=False), now=T0 + 60)
    assert job_rows(504)[0]["ended_at"] is None
    history.observe(reading(504, "printing", progress=40), now=T0 + 120)   # back online, same print
    assert len(job_rows(504)) == 1


def test_new_file_closes_previous_as_interrupted(client):
    history.observe(reading(505, "printing", job="a.gcode"), now=T0)
    history.observe(reading(505, "printing", job="b.gcode"), now=T0 + 60)
    a, b = job_rows(505)
    assert a["status"] == "interrupted" and b["status"] == "printing"


def test_print_seen_partway_is_backdated(client):
    history.observe(reading(506, "printing", progress=50, elapsed_seconds=7200), now=T0)
    assert job_rows(506)[0]["started_at"] == T0 - 7200


def test_no_duplicate_when_entry_already_open(client):
    # Another copy of the server (e.g. during a restart) already recorded this print
    c = history._db()
    c.execute("INSERT INTO print_jobs(printer_id,printer_name,file,status,started_at) VALUES(507,'P','part.gcode','printing',?)", (T0 - 500,))
    c.commit(); c.close()
    history.open_jobs.pop(507, None)
    history.observe(reading(507, "printing", progress=10), now=T0)
    rows = job_rows(507)
    assert len(rows) == 1 and rows[0]["started_at"] == T0 - 500


def test_klipper_import_merges_and_dedupes(client):
    printer = {"id": 508, "name": "Klipper", "base_url": "http://127.0.0.1:9"}
    # The dashboard recorded this print; Klipper also remembers it (start 2 minutes apart)
    history.observe(reading(508, "printing", job="bracket.gcode"), now=T0)
    history.observe(reading(508, "complete", job="bracket.gcode", progress=100), now=T0 + 3000)
    jobs = [
        {"job_id": "0001", "filename": "sub/bracket.gcode", "status": "completed", "start_time": T0 + 120, "end_time": T0 + 3000,
         "print_duration": 2800, "filament_used": 4200},
        {"job_id": "0002", "filename": "old.gcode", "status": "cancelled", "start_time": T0 - 90000, "end_time": T0 - 86400},
        {"job_id": "0003", "filename": "now.gcode", "status": "in_progress", "start_time": T0},
    ]
    assert history.import_printer(printer, jobs) == {"added": 1, "merged": 1}
    assert history.import_printer(printer, jobs) == {"added": 0, "merged": 0}   # second import changes nothing
    rows = job_rows(508)
    assert len(rows) == 2
    merged = next(r for r in rows if r["file"] == "bracket.gcode")
    assert merged["filament_mm"] == 4200 and merged["print_seconds"] == 2800 and merged["source_id"] == "0001"


def test_deleted_imported_job_stays_deleted(client):
    printer = {"id": 509, "name": "Klipper", "base_url": "http://127.0.0.1:9"}
    jobs = [{"job_id": "0009", "filename": "x.gcode", "status": "completed", "start_time": T0, "end_time": T0 + 60}]
    history.import_printer(printer, jobs)
    jid = job_rows(509)[0]["id"]
    assert client.delete(f"/api/history/{jid}").status_code == 200
    history.import_printer(printer, jobs)
    listed = client.get("/api/history", params={"printer_id": 509}).json()
    assert listed["total"] == 0


def test_history_api(client):
    r = client.get("/api/history/stats", params={"days": 0}).json()
    assert {"totals", "printers", "daily"} <= r.keys() and len(r["daily"]) == 90
    assert client.get("/api/history", params={"status": "completed", "limit": 5}).status_code == 200
    # Running prints can't be deleted
    history.observe(reading(510, "printing"), now=T0)
    assert client.delete(f"/api/history/{job_rows(510)[0]['id']}").status_code == 409


def test_daily_hours_split_across_days(client):
    from datetime import datetime, timedelta
    import time as _t
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = (today - timedelta(hours=2)).timestamp()     # 10 PM yesterday
    end = (today + timedelta(hours=3)).timestamp()      # 3 AM today
    if end > _t.time():
        return  # too early in the day to test "3 AM today" as finished
    c = history._db()
    c.execute("INSERT INTO print_jobs(printer_id,printer_name,file,status,started_at,ended_at) VALUES(511,'P','overnight.gcode','completed',?,?)", (start, end))
    c.commit(); c.close()
    daily = {d["day"]: d["hours"] for d in client.get("/api/history/stats", params={"days": 7}).json()["daily"]}
    assert daily[(today - timedelta(days=1)).strftime("%Y-%m-%d")] >= 2
    assert daily[today.strftime("%Y-%m-%d")] >= 3
    assert all(h <= 24 * 20 for h in daily.values())


def test_interrupted_import_uses_time_actually_run(client):
    printer = {"id": 512, "name": "Klipper", "base_url": "http://127.0.0.1:9"}
    # Klipper marked this job interrupted 74 days after it started, when it next restarted
    jobs = [{"job_id": "0012", "filename": "rack.gcode", "status": "interrupted", "start_time": T0,
             "end_time": T0 + 74 * 86400, "total_duration": 5 * 3600, "print_duration": 4 * 3600}]
    history.import_printer(printer, jobs)
    j = job_rows(512)[0]
    assert j["status"] == "interrupted" and j["ended_at"] - j["started_at"] == 5 * 3600


def test_interrupted_import_that_never_printed(client):
    printer = {"id": 513, "name": "Klipper", "base_url": "http://127.0.0.1:9"}
    jobs = [{"job_id": "0013", "filename": "never.gcode", "status": "interrupted", "start_time": T0,
             "end_time": T0 + 74 * 86400, "total_duration": 0, "print_duration": 0}]
    history.import_printer(printer, jobs)
    j = job_rows(513)[0]
    assert j["ended_at"] == j["started_at"]

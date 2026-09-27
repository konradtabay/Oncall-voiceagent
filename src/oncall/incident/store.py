"""SQLite persistence for incidents, alert queue, and turn queue."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from oncall.incident.models import Incident, QueuedAlert


class Store:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                to_number TEXT NOT NULL,
                summary TEXT NOT NULL,
                logs TEXT NOT NULL,
                verify_target TEXT NOT NULL,
                brief TEXT NOT NULL,
                fix TEXT NOT NULL,
                armed INTEGER NOT NULL DEFAULT 0,
                fixing INTEGER NOT NULL DEFAULT 0,
                agent_id TEXT NOT NULL DEFAULT '',
                call_sid TEXT NOT NULL DEFAULT '',
                run_locked INTEGER NOT NULL DEFAULT 0,
                issues TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS queued_alerts (
                id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                logs TEXT NOT NULL,
                verify_target TEXT NOT NULL,
                to_number TEXT NOT NULL,
                created_order INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS turn_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                text TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS call_transcripts (
                incident_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                transcript_text TEXT NOT NULL DEFAULT '',
                transcript_json TEXT NOT NULL DEFAULT '{}',
                fetched_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS call_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        self._conn.commit()
        self._migrate_incidents()

    def insert_incident(self, incident: Incident) -> None:
        self._conn.execute(
            """
            INSERT INTO incidents (
                id, state, to_number, summary, logs, verify_target,
                brief, fix, armed, fixing, agent_id, call_sid,
                conversation_id, run_locked, issues
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._incident_row(incident),
        )
        self._conn.commit()

    def get(self, incident_id: str) -> Optional[Incident]:
        row = self._conn.execute(
            "SELECT * FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_incident(row)

    def save(self, incident: Incident) -> None:
        existing = self.get(incident.id)
        if existing is None:
            self.insert_incident(incident)
            return
        self._conn.execute(
            """
            UPDATE incidents SET
                state = ?, to_number = ?, summary = ?, logs = ?,
                verify_target = ?, brief = ?, fix = ?, armed = ?,
                fixing = ?, agent_id = ?, call_sid = ?,
                conversation_id = ?, run_locked = ?,
                issues = ?
            WHERE id = ?
            """,
            (
                incident.state,
                incident.to_number,
                incident.summary,
                incident.logs,
                incident.verify_target,
                incident.brief,
                incident.fix,
                int(incident.armed),
                int(incident.fixing),
                incident.agent_id,
                incident.call_sid,
                incident.conversation_id,
                int(incident.run_locked),
                json.dumps(incident.issues),
                incident.id,
            ),
        )
        self._conn.commit()

    def active(self) -> Optional[Incident]:
        row = self._conn.execute(
            """
            SELECT * FROM incidents
            WHERE state NOT IN ('queued', 'closed', 'dropped')
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return self._row_to_incident(row)

    def enqueue(self, alert: QueuedAlert) -> None:
        if alert.created_order <= 0:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(created_order), 0) + 1 AS next_order FROM queued_alerts"
            ).fetchone()
            alert.created_order = int(row["next_order"])
        self._conn.execute(
            """
            INSERT INTO queued_alerts (
                id, summary, logs, verify_target, to_number, created_order
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                alert.id,
                alert.summary,
                alert.logs,
                alert.verify_target,
                alert.to_number,
                alert.created_order,
            ),
        )
        self._conn.commit()

    def pop_next(self) -> Optional[QueuedAlert]:
        row = self._conn.execute(
            """
            SELECT * FROM queued_alerts
            ORDER BY created_order ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        self._conn.execute(
            "DELETE FROM queued_alerts WHERE id = ?",
            (row["id"],),
        )
        self._conn.commit()
        return QueuedAlert(
            id=row["id"],
            summary=row["summary"],
            logs=row["logs"],
            verify_target=row["verify_target"],
            to_number=row["to_number"],
            created_order=int(row["created_order"]),
        )

    def latest_for_number(self, to_number: str) -> Optional[Incident]:
        row = self._conn.execute(
            """
            SELECT * FROM incidents
            WHERE to_number = ?
            ORDER BY
                CASE state
                    WHEN 'in_call' THEN 0
                    WHEN 'text_session' THEN 1
                    WHEN 'ringing' THEN 2
                    WHEN 'diagnosing' THEN 3
                    ELSE 4
                END,
                rowid DESC
            LIMIT 1
            """,
            (to_number,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_incident(row)

    def set_run_lock(self, incident_id: str, locked: bool) -> None:
        self._conn.execute(
            "UPDATE incidents SET run_locked = ? WHERE id = ?",
            (int(locked), incident_id),
        )
        self._conn.commit()

    def enqueue_turn(self, incident_id: str, text: str) -> None:
        self._conn.execute(
            "INSERT INTO turn_queue (incident_id, text) VALUES (?, ?)",
            (incident_id, text),
        )
        self._conn.commit()

    def _migrate_incidents(self) -> None:
        cols = {
            row[1] for row in self._conn.execute("PRAGMA table_info(incidents)")
        }
        if "conversation_id" not in cols:
            self._conn.execute(
                "ALTER TABLE incidents ADD COLUMN conversation_id TEXT NOT NULL DEFAULT ''"
            )
            self._conn.commit()

    def append_call_log(self, incident_id: str, kind: str, body: str) -> None:
        self._conn.execute(
            "INSERT INTO call_log (incident_id, kind, body) VALUES (?, ?, ?)",
            (incident_id, kind, body),
        )
        self._conn.commit()

    def save_call_transcript(
        self,
        incident_id: str,
        conversation_id: str,
        summary: str,
        transcript_text: str,
        transcript_json: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO call_transcripts (
                incident_id, conversation_id, summary, transcript_text,
                transcript_json, fetched_at
            ) VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(incident_id) DO UPDATE SET
                conversation_id = excluded.conversation_id,
                summary = excluded.summary,
                transcript_text = excluded.transcript_text,
                transcript_json = excluded.transcript_json,
                fetched_at = excluded.fetched_at
            """,
            (
                incident_id,
                conversation_id,
                summary,
                transcript_text,
                transcript_json,
            ),
        )
        self._conn.commit()

    def get_call_transcript(self, incident_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM call_transcripts WHERE incident_id = ?",
            (incident_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_call_logs(self, incident_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT kind, body, created_at FROM call_log WHERE incident_id = ? ORDER BY id",
            (incident_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def pop_turn(self, incident_id: str) -> Optional[str]:
        row = self._conn.execute(
            """
            SELECT id, text FROM turn_queue
            WHERE incident_id = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (incident_id,),
        ).fetchone()
        if row is None:
            return None
        self._conn.execute("DELETE FROM turn_queue WHERE id = ?", (row["id"],))
        self._conn.commit()
        return row["text"]

    @staticmethod
    def _incident_row(incident: Incident) -> tuple:
        return (
            incident.id,
            incident.state,
            incident.to_number,
            incident.summary,
            incident.logs,
            incident.verify_target,
            incident.brief,
            incident.fix,
            int(incident.armed),
            int(incident.fixing),
            incident.agent_id,
            incident.call_sid,
            incident.conversation_id,
            int(incident.run_locked),
            json.dumps(incident.issues),
        )

    @staticmethod
    def _row_to_incident(row: sqlite3.Row) -> Incident:
        keys = row.keys()
        return Incident(
            id=row["id"],
            state=row["state"],
            to_number=row["to_number"],
            summary=row["summary"],
            logs=row["logs"],
            verify_target=row["verify_target"],
            brief=row["brief"],
            fix=row["fix"],
            armed=bool(row["armed"]),
            fixing=bool(row["fixing"]),
            agent_id=row["agent_id"],
            call_sid=row["call_sid"],
            conversation_id=row["conversation_id"] if "conversation_id" in keys else "",
            run_locked=bool(row["run_locked"]),
            issues=json.loads(row["issues"] or "[]"),
        )

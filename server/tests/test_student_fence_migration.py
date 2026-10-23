"""Upgrade preserves existing child restrictions without linking siblings."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_student_fence_migration(tmp_path):
    path = tmp_path / 'migration.db'
    env = dict(os.environ, DATABASE_URL=f'sqlite:///{path}', ENV='test')
    def migrate(*args):
        result = subprocess.run([sys.executable, '-m', 'alembic', *args],
            cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    migrate('upgrade', 'e4b271d9c8a0')
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO families (id, access_disabled, created_at) VALUES (1, 0, CURRENT_TIMESTAMP)')
        db.execute('''INSERT INTO family_settings
            (family_id,daily_message_cap,review_enabled,quiet_enabled,quiet_start,quiet_end,
             daily_minutes_cap,notify_fence,forbidden_words_json,created_at)
            VALUES (1,200,1,1,22,6,60,1,'["GAME"]',CURRENT_TIMESTAMP)''')
        for sid, active in [(1, 1), (2, 1), (3, 0)]:
            db.execute('''INSERT INTO students
                (id,family_id,nickname,grade_band,device_id,active,token_version,created_at)
                VALUES (?,1,'孩子','8-12',?,?,1,CURRENT_TIMESTAMP)''', (sid, str(sid), active))
    migrate('upgrade', 'head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT fence_level,forbidden_words_json FROM students ORDER BY id').fetchall() == [
            ('strict', '["GAME"]'), ('strict', '["GAME"]'), ('strict', '[]')]
        db.execute("UPDATE students SET fence_level='off',forbidden_words_json='[]' WHERE id=1")
        assert db.execute('SELECT fence_level,forbidden_words_json FROM students WHERE id=2').fetchone() == ('strict', '["GAME"]')
    migrate('downgrade', 'e4b271d9c8a0')
    with sqlite3.connect(path) as db:
        assert 'fence_level' not in [r[1] for r in db.execute('PRAGMA table_info(students)')]
        assert db.execute('SELECT forbidden_words_json FROM family_settings').fetchone() == ('["GAME"]',)

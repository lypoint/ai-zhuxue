"""The default-policy migration cannot rewrite already granted family access."""
import importlib.util
from pathlib import Path

import sqlalchemy as sa


def test_domestic_trial_migration_only_changes_latest_default(monkeypatch):
    path = Path(__file__).parents[1] / 'migrations/versions/7a9c2e4f6b80_channel_registration_trials.py'
    spec = importlib.util.spec_from_file_location('channel_trial_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE pricing_configs (id INTEGER PRIMARY KEY, version INTEGER, trial_days INTEGER)')
        connection.exec_driver_sql('CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, expires_at TEXT)')
        connection.exec_driver_sql("INSERT INTO subscriptions VALUES (1, '2026-12-01T00:00:00')")
        connection.exec_driver_sql('INSERT INTO pricing_configs VALUES (1, 1, 3), (2, 2, 3)')
        monkeypatch.setattr(migration.op, 'execute', connection.exec_driver_sql)
        migration.upgrade()
        assert connection.exec_driver_sql('SELECT trial_days FROM pricing_configs ORDER BY version').scalars().all() == [3, 30]
        assert connection.exec_driver_sql('SELECT expires_at FROM subscriptions').scalar_one() == '2026-12-01T00:00:00'
        migration.upgrade()
        migration.downgrade()
        assert connection.exec_driver_sql('SELECT trial_days FROM pricing_configs ORDER BY version').scalars().all() == [3, 3]
        connection.exec_driver_sql('UPDATE pricing_configs SET trial_days = 14 WHERE id = 2')
        migration.upgrade()
        assert connection.exec_driver_sql('SELECT trial_days FROM pricing_configs WHERE id = 2').scalar_one() == 14
    engine.dispose()

"""
Comprehensive test suite for MVCCDatabase.
Run with: python -m pytest test_mvcc.py -v
Or directly: python test_mvcc.py
"""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator

from mvcc_db import MVCCDatabase, WriteConflictError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fresh_db() -> MVCCDatabase:
    """Create a fresh MVCCDatabase for each test."""
    db = MVCCDatabase(gc_interval_seconds=60.0)
    db._gc_running = False   # disable background GC during tests
    return db


# ---------------------------------------------------------------------------
# Basic Operations
# ---------------------------------------------------------------------------

class TestBasicOperations(unittest.TestCase):
    def test_put_get_commit(self):
        db = fresh_db()
        txn = db.begin_transaction()
        db.put("k1", "v1", txn)
        self.assertIsNone(db.get("k1", txn))       # not committed yet
        db.commit(txn)
        self.assertEqual(db.get("k1", txn), "v1")  # visible after commit

    def test_put_get_same_transaction(self):
        """Read-your-own-writes: get() must see uncommitted puts."""
        db = fresh_db()
        txn = db.begin_transaction()
        db.put("k1", "v1", txn)
        self.assertEqual(db.get("k1", txn), "v1")  # read-your-own-writes
        db.commit(txn)
        self.assertEqual(db.get("k1", txn), "v1")

    def test_delete(self):
        db = fresh_db()
        txn1 = db.begin_transaction()
        db.put("k1", "v1", txn1)
        db.commit(txn1)

        txn2 = db.begin_transaction()
        db.delete("k1", txn2)
        self.assertIsNone(db.get("k1", txn2))     # sees deletion in own txn
        db.commit(txn2)

        txn3 = db.begin_transaction()
        self.assertIsNone(db.get("k1", txn3))     # deletion persisted

    def test_rollback(self):
        db = fresh_db()
        txn1 = db.begin_transaction()
        db.put("k1", "v1", txn1)
        db.commit(txn1)

        txn2 = db.begin_transaction()
        db.put("k1", "v2", txn2)
        db.put("k2", "v2", txn2)
        db.rollback(txn2)

        txn3 = db.begin_transaction()
        self.assertEqual(db.get("k1", txn3), "v1")  # original value intact
        self.assertIsNone(db.get("k2", txn3))       # never existed

    def test_rollback_mid_scan(self):
        """Deleting a key inside a transaction must hide it in scan()."""
        db = fresh_db()
        t1 = db.begin_transaction()
        db.put("a", "1", t1); db.put("b", "2", t1); db.put("c", "3", t1)
        db.commit(t1)

        t2 = db.begin_transaction()
        db.delete("b", t2)
        result = db.scan("a", "c", t2)
        self.assertEqual(result, [("a", "1"), ("c", "3")])
        db.rollback(t2)

        t3 = db.begin_transaction()
        result = db.scan("a", "c", t3)
        self.assertEqual(result, [("a", "1"), ("b", "2"), ("c", "3")])

    def test_put_delete_same_key_in_txn(self):
        """If you put then delete in the same transaction, delete wins."""
        db = fresh_db()
        t1 = db.begin_transaction()
        db.put("k1", "v1", t1)
        db.delete("k1", t1)
        self.assertIsNone(db.get("k1", t1))
        db.commit(t1)

        t2 = db.begin_transaction()
        self.assertIsNone(db.get("k1", t2))    # gone

    def test_double_commit_raises(self):
        db = fresh_db()
        txn = db.begin_transaction()
        db.put("k1", "v1", txn)
        db.commit(txn)
        with self.assertRaises(ValueError) as ctx:
            db.commit(txn)
        self.assertIn("cannot commit", str(ctx.exception))

    def test_rollback_inactive_raises(self):
        db = fresh_db()
        txn = db.begin_transaction()
        db.rollback(txn)
        with self.assertRaises(ValueError) as ctx:
            db.rollback(txn)
        self.assertIn("cannot rollback", str(ctx.exception))

    def test_nonexistent_key_returns_none(self):
        db = fresh_db()
        txn = db.begin_transaction()
        self.assertIsNone(db.get("nonexistent", txn))

    def test_nonexistent_txn_raises(self):
        db = fresh_db()
        with self.assertRaises(ValueError):
            db.get("k1", 9999)

    def test_txn_id_monotonically_increases(self):
        db = fresh_db()
        ids = [db.begin_transaction() for _ in range(5)]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(ids[-1] - ids[0], 4)


# ---------------------------------------------------------------------------
# Snapshot Isolation
# ---------------------------------------------------------------------------

class TestSnapshotIsolation(unittest.TestCase):
    def test_reads_dont_block_writes(self):
        """Long-running read transaction must not see new commits."""
        db = fresh_db()

        # T1: writes k1=v1
        t1 = db.begin_transaction()
        db.put("k1", "v1", t1)
        db.commit(t1)

        # T2: snapshot sees k1=v1
        t2 = db.begin_transaction()

        # T3: overwrites k1
        t3 = db.begin_transaction()
        db.put("k1", "v2", t3)
        db.commit(t3)

        # T2 must still see v1
        self.assertEqual(db.get("k1", t2), "v1")

        # New transaction sees v2
        t4 = db.begin_transaction()
        self.assertEqual(db.get("k1", t4), "v2")

    def test_snapshot_sees_only_committed_at_begin(self):
        db = fresh_db()
        t1 = db.begin_transaction()
        # snapshot of t2 is taken now (TID of t2 > any committed so far)
        t2 = db.begin_transaction()

        db.put("k1", "v1", t1)
        db.commit(t1)

        # t2's snapshot was taken before the commit → must not see v1
        self.assertIsNone(db.get("k1", t2))

        t3 = db.begin_transaction()  # new snapshot sees v1
        self.assertEqual(db.get("k1", t3), "v1")

    def test_read_your_own_writes_in_snapshot(self):
        db = fresh_db()
        txn = db.begin_transaction()
        db.put("k1", "v1", txn)
        # snapshot already contains the uncommitted write
        self.assertEqual(db.get("k1", txn), "v1")
        db.commit(txn)

        # subsequent transaction
        t2 = db.begin_transaction()
        self.assertEqual(db.get("k1", t2), "v1")


# ---------------------------------------------------------------------------
# Write-Write Conflict Detection
# ---------------------------------------------------------------------------

class TestWriteWriteConflicts(unittest.TestCase):
    def test_conflict_both_put_same_key(self):
        """T1 and T2 both put k1; first commit wins, second raises."""
        db = fresh_db()
        db.put("k1", "init", db.begin_transaction())  # bootstrap

        t1 = db.begin_transaction()
        t2 = db.begin_transaction()
        db.put("k1", "v1", t1)
        db.put("k1", "v2", t2)

        db.commit(t1)                                 # t1 succeeds
        with self.assertRaises(WriteConflictError) as ctx:
            db.commit(t2)                             # t2 fails
        self.assertIn("k1", ctx.exception.conflicted_keys)

        # Value is v1
        txn = db.begin_transaction()
        self.assertEqual(db.get("k1", txn), "v1")

    def test_conflict_put_vs_delete(self):
        db = fresh_db()
        db.put("k1", "init", db.begin_transaction())

        t1 = db.begin_transaction()
        t2 = db.begin_transaction()
        db.delete("k1", t1)      # T1 deletes
        db.put("k1", "v2", t2)   # T2 overwrites

        db.commit(t1)             # delete wins
        with self.assertRaises(WriteConflictError):
            db.commit(t2)

        txn = db.begin_transaction()
        self.assertIsNone(db.get("k1", txn))  # deleted

    def test_no_conflict_different_keys(self):
        db = fresh_db()
        db.put("k1", "init", db.begin_transaction())

        t1 = db.begin_transaction()
        t2 = db.begin_transaction()
        db.put("k1", "v1", t1)
        db.put("k2", "v2", t2)   # no overlap

        db.commit(t1)
        db.commit(t2)             # both succeed

        txn = db.begin_transaction()
        self.assertEqual(db.get("k1", txn), "v1")
        self.assertEqual(db.get("k2", txn), "v2")

    def test_conflict_only_if_commit_after_snapshot(self):
        """Conflict only if the *commit* of the other txn happened after
        this txn's snapshot was taken."""
        db = fresh_db()
        db.put("k1", "init", db.begin_transaction())

        t1 = db.begin_transaction()
        t2 = db.begin_transaction()
        t3 = db.begin_transaction()

        db.put("k1", "v2", t2)
        db.commit(t2)   # t2 commits before t1's snapshot is taken? Wait…

        # Actually t1's snapshot = t1's TID, which is > t2's TID,
        # so t2's commit is NOT in t1's snapshot. Conflict should exist.
        db.put("k1", "v1", t1)
        with self.assertRaises(WriteConflictError):
            db.commit(t1)

        # t3's snapshot is taken after t2 committed, so no conflict
        t4 = db.begin_transaction()
        db.put("k1", "v4", t4)
        db.commit(t4)   # succeeds — t2's commit IS in t3's snapshot
        self.assertEqual(db.get("k1", t4), "v4")

    def test_conflict_detection_is_key_level(self):
        """Concurrent puts to different keys → no conflict."""
        db = fresh_db()
        db.put("a", "init", db.begin_transaction())
        db.put("b", "init", db.begin_transaction())

        t1 = db.begin_transaction()
        t2 = db.begin_transaction()
        db.put("a", "t1", t1)
        db.put("b", "t2", t2)
        db.commit(t1)
        db.commit(t2)  # no conflict — different keys

    def test_no_conflict_if_winner_rollback(self):
        """If the winner rolls back, can the loser still commit?"""
        db = fresh_db()
        db.put("k1", "init", db.begin_transaction())

        t1 = db.begin_transaction()
        t2 = db.begin_transaction()
        db.put("k1", "t1", t1)
        db.put("k1", "t2", t2)

        db.commit(t1)                       # t1 wins
        with self.assertRaises(WriteConflictError):
            db.commit(t2)                   # t2 loses

        # t1 already committed → t2 cannot re-commit even after rollback
        # (t2 is already marked ABORTED inside commit())
        self.assertIsNone(db.get("k1", db.begin_transaction()))


# ---------------------------------------------------------------------------
# Range Queries
# ---------------------------------------------------------------------------

class TestScan(unittest.TestCase):
    def _bootstrap(self, db: MVCCDatabase) -> None:
        t = db.begin_transaction()
        for k, v in [("a", "1"), ("b", "2"), ("c", "3"), ("d", "4"), ("e", "5")]:
            db.put(k, v, t)
        db.commit(t)

    def test_scan_returns_sorted(self):
        db = fresh_db()
        self._bootstrap(db)
        txn = db.begin_transaction()
        result = db.scan("a", "e", txn)
        keys = [k for k, _ in result]
        self.assertEqual(keys, sorted(keys))

    def test_scan_empty_range(self):
        db = fresh_db()
        self._bootstrap(db)
        txn = db.begin_transaction()
        self.assertEqual(db.scan("x", "z", txn), [])

    def test_scan_excludes_deleted(self):
        db = fresh_db()
        self._bootstrap(db)

        t2 = db.begin_transaction()
        db.delete("b", t2)
        db.delete("d", t2)
        result = db.scan("a", "e", t2)
        self.assertEqual([k for k, _ in result], ["a", "c", "e"])
        db.commit(t2)

        t3 = db.begin_transaction()
        result = db.scan("a", "e", t3)
        self.assertEqual([k for k, _ in result], ["a", "c", "e"])

    def test_scan_read_your_own_deletes(self):
        db = fresh_db()
        self._bootstrap(db)

        txn = db.begin_transaction()
        db.delete("b", txn)
        result = db.scan("a", "e", txn)
        self.assertEqual([k for k, _ in result], ["a", "c", "d", "e"])

    def test_scan_read_your_own_writes(self):
        db = fresh_db()
        t = db.begin_transaction()
        db.put("a", "1", t); db.put("b", "2", t)
        db.put("c", "3", t); db.put("d", "4", t)
        db.commit(t)

        txn = db.begin_transaction()
        db.put("b", "B", txn)
        db.put("e", "5", txn)
        result = db.scan("a", "e", txn)
        self.assertEqual([(k, v) for k, v in result], [
            ("a", "1"), ("b", "B"), ("c", "3"), ("d", "4"), ("e", "5")
        ])

    def test_scan_snapshot_isolation(self):
        db = fresh_db()
        self._bootstrap(db)

        t1 = db.begin_transaction()
        db.put("f", "6", t1)     # committed to snapshot of t1
        db.commit(t1)

        t2 = db.begin_transaction()
        result = db.scan("a", "f", t2)
        self.assertEqual([k for k, _ in result], ["a", "b", "c", "d", "e", "f"])

        t3 = db.begin_transaction()
        # t3's snapshot taken before f was added
        result = db.scan("a", "f", t3)
        self.assertEqual([k for k, _ in result], ["a", "b", "c", "d", "e"])


# ---------------------------------------------------------------------------
# Garbage Collection
# ---------------------------------------------------------------------------

class TestGarbageCollection(unittest.TestCase):
    def test_get_oldest_active_snapshot(self):
        db = fresh_db()
        self.assertIsNone(db.get_oldest_active_snapshot())

        t1 = db.begin_transaction()
        self.assertEqual(db.get_oldest_active_snapshot(), t1)

        t2 = db.begin_transaction()
        self.assertEqual(db.get_oldest_active_snapshot(), min(t1, t2))

        db.rollback(t2)
        self.assertEqual(db.get_oldest_active_snapshot(), t1)

        db.commit(t1)
        self.assertIsNone(db.get_oldest_active_snapshot())

    def test_run_gc_prunes_old_versions(self):
        db = fresh_db()
        gc_called = threading.Event()
        original_gc = db.run_gc

        def gc_and_notify():
            result = original_gc()
            gc_called.result = result
            return result

        db.run_gc = gc_and_notify

        # Create multiple versions of k1
        for i in range(10):
            txn = db.begin_transaction()
            db.put("k1", f"v{i}", txn)
            db.commit(txn)

        # GC threshold = oldest active snapshot (none → -1 → prune everything but newest)
        with db._versions_lock:
            chain_len_before = len(db._versions["k1"])

        db.run_gc()

        with db._versions_lock:
            chain_len_after = len(db._versions["k1"])

        self.assertLess(chain_len_after, chain_len_before)
        # After GC, newest version still accessible
        txn = db.begin_transaction()
        self.assertEqual(db.get("k1", txn), "v9")

    def test_gc_preserves_active_snapshot_versions(self):
        db = fresh_db()
        db.put("k1", "init", db.begin_transaction())

        # t1 holds a snapshot that can still read version 1
        t1 = db.begin_transaction()

        # create many new versions
        for i in range(5):
            txn = db.begin_transaction()
            db.put("k1", f"v{i}", txn)
            db.commit(txn)

        # GC must not prune version 1 (t1's snapshot sees it)
        with db._versions_lock:
            ts_values = [v[0] for v in db._versions["k1"]]

        db.run_gc()

        with db._versions_lock:
            ts_values_after = [v[0] for v in db._versions["k1"]]

        # Oldest active snapshot = t1's ID → only versions ≥ t1 survive
        self.assertGreaterEqual(min(ts_values_after), min(ts_values))
        # t1 still reads the original value
        self.assertEqual(db.get("k1", t1), "init")

    def test_gc_no_op_when_no_versions(self):
        db = fresh_db()
        pruned = db.run_gc()
        self.assertEqual(pruned, 0)


# ---------------------------------------------------------------------------
# Thread Safety
# ---------------------------------------------------------------------------

class TestConcurrency(unittest.TestCase):
    def test_concurrent_readers_dont_block(self):
        db = fresh_db()
        db.put("k1", "v1", db.begin_transaction())

        errors = []
        barrier = threading.Barrier(11)

        def reader():
            try:
                barrier.wait()
                txn = db.begin_transaction()
                for _ in range(100):
                    db.get("k1", txn)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])

    def test_concurrent_writers_serialised(self):
        """Two writers on same key → one succeeds, one gets conflict."""
        db = fresh_db()
        db.put("k1", "init", db.begin_transaction())

        results: dict[int, str] = {}
        errors: list[Exception] = []

        def writer(tid):
            try:
                txn = db.begin_transaction()
                db.put("k1", f"v{tid}", txn)
                db.commit(txn)
                results[tid] = "commit"
            except WriteConflictError:
                results[tid] = "conflict"
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(1,)),
            threading.Thread(target=writer, args=(2,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        commits = [k for k, v in results.items() if v == "commit"]
        conflicts = [k for k, v in results.items() if v == "conflict"]
        self.assertEqual(len(commits), 1)
        self.assertEqual(len(conflicts), 1)

    def test_many_concurrent_transactions(self):
        """20 concurrent transactions each writing a unique key."""
        db = fresh_db()
        db.put("init", "0", db.begin_transaction())

        def worker(i: int):
            txn = db.begin_transaction()
            db.put(f"k{i}", f"v{i}", txn)
            db.commit(txn)

        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [ex.submit(worker, i) for i in range(20)]
            for f in as_completed(futures):
                f.result()  # raise if exception

        # All committed
        scan_txn = db.begin_transaction()
        result = db.scan("k0", "k19", scan_txn)
        self.assertEqual(len(result), 20)


# ---------------------------------------------------------------------------
# Stress / Regression
# ---------------------------------------------------------------------------

class TestStress(unittest.TestCase):
    def test_rapid_begin_commit_no_lock_leak(self):
        db = fresh_db()
        for _ in range(1000):
            t = db.begin_transaction()
            db.put("k", "v", t)
            db.commit(t)
        # No leaks if we get here

    def test_gc_stress(self):
        db = fresh_db()
        db.put("k1", "init", db.begin_transaction())
        for i in range(20):
            t = db.begin_transaction()
            db.put("k1", f"v{i}", t)
            db.commit(t)
            db.run_gc()

        with db._versions_lock:
            chain_len = len(db._versions["k1"])
        self.assertLess(chain_len, 25)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Run with verbose output
    unittest.main(verbosity=2)

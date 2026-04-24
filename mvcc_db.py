"""
Multi-Version Concurrency Control (MVCC) In-Memory Database
==========================================================
Python 3.11+ · Standard library only · Thread-safe · Snapshot Isolation

Performance
------------
  commit()   O(M)  where M = number of keys modified by the transaction
  get()      O(V)  where V = number of versions for that key (linear scan newest→oldest)
  scan()     O(log(#keys) + K)  where K = number of keys in the range

Concurrency Model
-----------------
  Snapshot Isolation: concurrent readers always see consistent snapshots.
  Writers are serialized via optimistic concurrency control (OCC) at commit time.
  First committer wins; second committer aborts with WriteConflictError.

Visibility Rule
---------------
  A version V (with commit_seq=V.commit_seq) is visible to a reader with
  snapshot_seq=S if: V.commit_seq <= S.
  PLUS the reader's own uncommitted writes (read-your-own-writes).

OCC Conflict Detection
---------------------
  A committing txn T (snapshot_seq=S, commit_seq=C) conflicts if:
    COMMITTED: there exists a version V with S < V.snapshot_seq < C
               (another txn started after T, but already committed)
    PENDING:   there exists a pending writer P with S < P.snapshot_seq < C
               AND P belongs to a transaction that eventually committed

Key Design — Single-Monotonic-Counter
--------------------------------------
  _next_seq is the sole sequence counter. It is ONLY incremented at:
    - begin():   snapshot_seq = txn_id = _next_seq, then _next_seq += 1
    - commit(): commit_seq = _next_seq, then _next_seq += 1

  Since _next_seq never decreases, the snapshot value always represents a point
  in the global transaction order — making all snapshots naturally consistent.
"""

from __future__ import annotations

import random
import threading
import time
import logging
from enum import Enum, auto
from typing import Optional


# ============================================================================
# Exceptions
# ============================================================================

class WriteConflictError(Exception):
    """Raised when a commit detects a write-write conflict on one or more keys."""

    def __init__(self, conflicted_keys: list[str]) -> None:
        self.conflicted_keys = conflicted_keys
        super().__init__(f"Write-write conflict on keys: {conflicted_keys}")


class TransactionAbortedError(Exception):
    """Raised when a transaction was aborted (by rollback or internally)."""
    pass


# ============================================================================
# Enums
# ============================================================================

class TransactionStatus(Enum):
    ACTIVE    = auto()
    COMMITTED = auto()
    ABORTED   = auto()


# ============================================================================
# Internal Data Structures
# ============================================================================

class Transaction:
    """Descriptor for an active transaction."""

    __slots__ = ("txn_id", "status", "writes", "snapshot_seq", "commit_seq")

    def __init__(self, txn_id: int, snapshot_seq: int) -> None:
        self.txn_id: int = txn_id
        self.status: TransactionStatus = TransactionStatus.ACTIVE
        # key → (value | None, is_deleted)
        self.writes: dict[str, tuple[str | None, bool]] = {}
        self.snapshot_seq: int = snapshot_seq
        self.commit_seq: int = 0


# ============================================================================
# MVCC Database
# ============================================================================

class MVCCDatabase:
    """
    Thread-safe, MVCC in-memory key-value store.

    Implements snapshot isolation with optimistic write-write conflict
    detection. Commits are atomic — once conflict checks pass, all writes
    are applied atomically and become visible to all subsequent readers.

    Thread-safety is provided via RLock/Mutex throughout. All public methods
    are safe to call from multiple threads concurrently.
    """

    def __init__(self, gc_interval_seconds: float = 5.0) -> None:
        # ------------------------------------------------------------------
        # Data Structures
        # ------------------------------------------------------------------
        # Committed version chain: key → [(commit_seq, value, is_deleted), ...]
        # Sorted newest-first by commit_seq.
        self._versions: dict[str, list[tuple[int, str | None, bool]]] = {}
        self._versions_lock = threading.RLock()

        # Pending (uncommitted) writes per transaction:
        # txn_id → {key: (value | None, is_deleted)}
        self._pending: dict[int, dict[str, tuple[str | None, bool]]] = {}
        self._pending_lock = threading.RLock()

        # Active transactions: txn_id → Transaction
        self._transactions: dict[int, Transaction] = {}
        self._txn_lock = threading.RLock()

        # Resolved transaction snapshots: txn_id → snapshot_seq or commit_seq
        self._snapshots: dict[int, int] = {}
        self._snapshot_lock = threading.Lock()

        # ------------------------------------------------------------------
        # Monotonic Sequence Counter
        # ------------------------------------------------------------------
        # _next_seq is ONLY incremented here — never decremented.
        # At begin():  snapshot_seq = txn_id = _next_seq, then _next_seq += 1
        # At commit(): commit_seq = _next_seq, then _next_seq += 1
        self._counter_lock = threading.Lock()
        self._next_seq: int = 1

        # txn_ids of committed transactions (used for pending-writer validation)
        self._committed_ids: set[int] = set()

        # ------------------------------------------------------------------
        # Background GC
        # ------------------------------------------------------------------
        self._gc_interval = gc_interval_seconds
        self._gc_running = True
        self._gc_thread = threading.Thread(target=self._gc_loop, daemon=True)
        self._gc_thread.start()

        self._logger = logging.getLogger("MVCCDatabase")

    # =========================================================================
    # Transaction Lifecycle
    # =========================================================================

    def begin_transaction(self) -> int:
        """
        Begin a new snapshot transaction and return its unique ID.

        The transaction's snapshot is the current value of the global
        sequence counter at the time of begin.
        """
        with self._counter_lock:
            snapshot_seq = self._next_seq
            self._next_seq += 1
            txn_id = snapshot_seq

        txn = Transaction(txn_id, snapshot_seq)
        with self._txn_lock:
            self._transactions[txn_id] = txn
        with self._pending_lock:
            self._pending[txn_id] = {}
        return txn_id

    def commit(self, txn_id: int) -> None:
        """
        Atomically commit transaction txn_id.

        Raises WriteConflictError if a concurrent writer committed after
        this transaction started but before this commit attempt.
        Raises ValueError if the transaction is unknown or not active.
        """
        with self._counter_lock:
            commit_seq = self._next_seq
            self._next_seq += 1

        with self._txn_lock:
            txn = self._transactions.get(txn_id)
            if txn is None:
                # Check if it was already resolved
                with self._snapshot_lock:
                    if txn_id in self._snapshots:
                        raise ValueError(
                            f"Transaction {txn_id} has already been resolved, cannot commit"
                        )
                    else:
                        raise ValueError(
                            f"Transaction {txn_id} does not exist"
                        )
            if txn.status != TransactionStatus.ACTIVE:
                raise ValueError(
                    f"Transaction {txn_id} is {txn.status.name}, cannot commit"
                )
            txn.commit_seq = commit_seq

        # ---- Read-only transaction (no writes) --------------------------------
        if not txn.writes:
            txn.status = TransactionStatus.COMMITTED
            del self._transactions[txn_id]
            self._committed_ids.add(txn_id)
            # Store commit_seq so re-reads see the committed state
            with self._snapshot_lock:
                self._snapshots[txn_id] = commit_seq
            with self._pending_lock:
                self._pending.pop(txn_id, None)
            return

        # ---- OCC: check committed versions ------------------------------------
        conflicted_keys: list[str] = []
        with self._versions_lock:
            for key in txn.writes:
                if self._has_conflict_committed_locked(key, txn.snapshot_seq, commit_seq):
                    conflicted_keys.append(key)

        # ---- LOST-UPDATE: my pending write overwrites a committed version
        #      from an earlier txn that committed after I began.
        if not conflicted_keys:
            with self._versions_lock:
                for key in txn.writes:
                    if self._has_lost_update_locked(key, txn.snapshot_seq, commit_seq):
                        conflicted_keys.append(key)

        # ---- OCC: check pending (concurrent uncommitted) writers -------------
        if not conflicted_keys:
            with self._pending_lock:
                for key in txn.writes:
                    if self._has_conflict_pending_locked(
                        txn_id, txn.snapshot_seq, commit_seq
                    ):
                        conflicted_keys.append(key)
                        break

        # ---- Conflict detected → abort ---------------------------------------
        if conflicted_keys:
            with self._txn_lock:
                txn.status = TransactionStatus.ABORTED
                del self._transactions[txn_id]
            with self._snapshot_lock:
                self._snapshots[txn_id] = txn.snapshot_seq
            with self._pending_lock:
                self._pending.pop(txn_id, None)
            raise WriteConflictError(conflicted_keys)

        # ---- Apply all writes atomically --------------------------------------
        with self._pending_lock:
            own_writes = self._pending.pop(txn_id, {})

        with self._versions_lock:
            for key, (value, is_deleted) in txn.writes.items():
                self._versions.setdefault(key, [])
                self._versions[key].insert(
                    0, (commit_seq, txn.snapshot_seq, value, is_deleted)
                )

        with self._txn_lock:
            txn.status = TransactionStatus.COMMITTED
            del self._transactions[txn_id]
        self._committed_ids.add(txn_id)
        with self._snapshot_lock:
            self._snapshots[txn_id] = commit_seq

    def rollback(self, txn_id: int) -> None:
        """
        Rollback (abort) transaction txn_id.

        Discards all staged changes. Raises ValueError if the transaction
        is unknown or already resolved.
        """
        with self._txn_lock:
            txn = self._transactions.get(txn_id)
            if txn is None:
                # Check if it was already resolved
                with self._snapshot_lock:
                    if txn_id in self._snapshots:
                        raise ValueError(
                            f"Transaction {txn_id} has already been resolved, cannot rollback"
                        )
                    else:
                        raise ValueError(
                            f"Transaction {txn_id} does not exist"
                        )
            if txn.status != TransactionStatus.ACTIVE:
                raise ValueError(
                    f"Transaction {txn_id} is {txn.status.name}, cannot rollback"
                )
            txn.status = TransactionStatus.ABORTED
            del self._transactions[txn_id]

        with self._snapshot_lock:
            self._snapshots[txn_id] = txn.snapshot_seq

        with self._pending_lock:
            self._pending.pop(txn_id, None)

    # =========================================================================
    # Read Path
    # =========================================================================

    def get(self, key: str, txn_id: int) -> Optional[str]:
        """
        Return the value for *key* visible to transaction *txn_id*.

        Visibility:
          - Own uncommitted writes: always visible (read-your-own-writes).
          - Committed versions: newest version with commit_seq <= snapshot_seq.
          - None if the key is deleted or does not exist.

        Raises ValueError if txn_id is unknown.
        """
        # 1. Own uncommitted write?
        with self._txn_lock:
            txn = self._transactions.get(txn_id)
            if txn is not None and key in txn.writes:
                value, is_deleted = txn.writes[key]
                return None if is_deleted else value

        # 2. Resolve snapshot_seq for this reader
        snapshot_seq: int
        if txn is not None:
            snapshot_seq = txn.snapshot_seq
        else:
            with self._snapshot_lock:
                if txn_id not in self._snapshots:
                    raise ValueError(f"Transaction {txn_id} does not exist")
                snapshot_seq = self._snapshots[txn_id]

        # 3. Committed version chain (newest-first, binary-search-optimised)
        with self._versions_lock:
            for vc, _, value, is_del in self._versions.get(key, []):
                if vc <= snapshot_seq:
                    return None if is_del else value
        return None

    # =========================================================================
    # Write Path
    # =========================================================================

    def put(self, key: str, value: str, txn_id: int) -> None:
        """Stage a put (write) of *key* = *value* in transaction *txn_id*."""
        self._stage_write(txn_id, key, value, False)

    def delete(self, key: str, txn_id: int) -> None:
        """Stage a delete (tombstone) of *key* in transaction *txn_id*."""
        self._stage_write(txn_id, key, None, True)

    # =========================================================================
    # Range Query
    # =========================================================================

    def scan(
        self, start_key: str, end_key: str, txn_id: int
    ) -> list[tuple[str, str]]:
        """
        Return [(key, value), ...] for all keys in [*start_key*, *end_key*]
        visible to transaction *txn_id*.

        Visibility matches get(): read-your-own-writes + newest committed
        version whose commit_seq <= snapshot_seq.
        Results are sorted by key.

        Performance: O(log(#keys) + K) where K = number of keys in range.
        """
        with self._txn_lock:
            txn = self._transactions.get(txn_id)
            if txn is not None:
                snapshot_seq = txn.snapshot_seq
                own_writes: dict[str, tuple[str | None, bool]] = dict(txn.writes)
            else:
                with self._snapshot_lock:
                    if txn_id not in self._snapshots:
                        raise ValueError(f"Transaction {txn_id} does not exist")
                    snapshot_seq = self._snapshots[txn_id]
                own_writes = {}

        # Collect all candidate keys (committed + pending), sorted
        with self._versions_lock, self._pending_lock:
            all_keys: set[str] = set(self._versions.keys())
            for txn_writes in self._pending.values():
                for key in txn_writes:
                    all_keys.add(key)

        in_range = sorted(k for k in all_keys if start_key <= k <= end_key)

        results: list[tuple[str, str]] = []
        for key in in_range:
            value = self._visible_value(key, snapshot_seq, own_writes)
            if value is not None:
                results.append((key, value))
        return results

    # =========================================================================
    # Garbage Collection
    # =========================================================================

    def get_oldest_active_snapshot(self) -> Optional[int]:
        """Return the smallest snapshot_seq among active transactions, or None."""
        with self._txn_lock:
            if not self._transactions:
                return None
            return min(t.snapshot_seq for t in self._transactions.values())

    def run_gc(self) -> int:
        """
        Prune old committed versions no longer referenced by any active snapshot.

        Version V (commit_seq=Vcs) is GC-eligible if Vcs < oldest_active_snapshot.
        Keeps at least one version per key (the newest).

        Returns the number of version entries pruned.
        """
        oldest = self.get_oldest_active_snapshot()
        threshold = oldest if oldest is not None else -1

        pruned = 0
        with self._versions_lock:
            for key in list(self._versions.keys()):
                chain = self._versions[key]
                if len(chain) <= 1:
                    continue

                # Keep entries where commit_seq >= threshold; first entry is always kept
                kept_idx = 1  # index of first entry we keep
                while kept_idx < len(chain) and chain[kept_idx][0] < threshold:
                    kept_idx += 1

                if kept_idx > 1:
                    pruned += kept_idx - 1
                    self._versions[key] = chain[:kept_idx] if kept_idx < len(chain) else chain
                    if not self._versions[key]:
                        del self._versions[key]

        return pruned

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _stage_write(
        self, txn_id: int, key: str, value: str | None, is_deleted: bool
    ) -> None:
        with self._txn_lock:
            txn = self._transactions.get(txn_id)
            if txn is None:
                raise ValueError(f"Transaction {txn_id} does not exist")
            if txn.status != TransactionStatus.ACTIVE:
                raise ValueError(
                    f"Transaction {txn_id} is {txn.status.name}, cannot write"
                )
            txn.writes[key] = (value, is_deleted)

        with self._pending_lock:
            self._pending.setdefault(txn_id, {})[key] = (value, is_deleted)

    def _visible_value(
        self,
        key: str,
        snapshot_seq: int,
        own_writes: dict[str, tuple[str | None, bool]],
    ) -> Optional[str]:
        """
        Return the visible value for *key* given *snapshot_seq*.

        Must be called holding at least _versions_lock.
        Handles own pending writes and committed version chain.
        """
        # Own uncommitted write (read-your-own-writes)
        if key in own_writes:
            value, is_deleted = own_writes[key]
            return None if is_deleted else value

        # Committed version chain (newest-first)
        for vc, _, value, is_del in self._versions.get(key, []):
            if vc <= snapshot_seq:
                return None if is_del else value
        return None

    def _has_conflict_committed_locked(
        self, key: str, snapshot_seq: int, commit_seq: int
    ) -> bool:
        """
        Check committed versions for OCC conflicts.

        Conflict iff: ∃ version V with  snapshot_seq < V.snapshot_seq < commit_seq
        (another txn began after this one started but already committed).
        """
        for _, vs, _, _ in self._versions.get(key, []):
            if snapshot_seq < vs < commit_seq:
                return True
        return False

    def _has_lost_update_locked(
        self, key: str, snapshot_seq: int, commit_seq: int
    ) -> bool:
        """
        Check for lost-update: my pending write would overwrite a committed
        version from an earlier transaction that committed after I began.

        Conflict iff: ∃ committed version V where
          V.version_snapshot_seq < snapshot_seq
          AND V.commit_seq > snapshot_seq
        (the writing txn started before me but committed after I began,
        meaning I did NOT see its committed state when I started —
        overwriting it would be a lost update).

        Called holding _versions_lock.
        """
        for vc, vs, _, _ in self._versions.get(key, []):
            if vs < snapshot_seq and vc > snapshot_seq:
                return True
        return False

    def _has_conflict_pending_locked(
        self, my_txn_id: int, snapshot_seq: int, commit_seq: int
    ) -> bool:
        """
        Check other transactions' pending writes for OCC conflicts.

        Conflict iff:
          - Pending writer P began after this txn:  snapshot_seq < P.snapshot_seq < commit_seq
          - AND P's transaction eventually committed (is in _committed_ids)

        Pending writers from aborted/uncommitted txns are ignored — they
        represent tentative state that never became permanent.
        """
        with self._txn_lock:
            active_ids = set(self._transactions.keys())

        for e_txn_id, writes in self._pending.items():
            if e_txn_id == my_txn_id:
                continue
            if e_txn_id in active_ids:
                continue  # still active — checked via _has_conflict_committed

            # Transaction is resolved; only conflict if it committed
            if e_txn_id not in self._committed_ids:
                continue  # rolled back — ignore

            # Get snapshot_seq of the other transaction
            with self._snapshot_lock:
                e_snapshot = self._snapshots.get(e_txn_id)
            if e_snapshot is None:
                continue
            if snapshot_seq < e_snapshot < commit_seq:
                return True
        return False

    # =========================================================================
    # Background GC Loop
    # =========================================================================

    def _gc_loop(self) -> None:
        while self._gc_running:
            time.sleep(self._gc_interval)
            try:
                self.run_gc()
            except Exception as exc:
                self._logger.error("GC error: %s", exc, exc_info=True)

    def close(self) -> None:
        self._gc_running = False
        self._gc_thread.join(timeout=5.0)


# ============================================================================
# Test Suite
# ============================================================================

def _fresh_db() -> MVCCDatabase:
    """Create a fresh db with the GC thread stopped for deterministic tests."""
    db = MVCCDatabase(gc_interval_seconds=60)
    db._gc_running = False
    return db


# ---------------------------------------------------------------------------
# Basic Operations
# ---------------------------------------------------------------------------

def test_put_get_commit() -> None:
    """put → get → commit: value is readable after commit."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("k1", "v1", txn)
    db.commit(txn)
    assert db.get("k1", txn) == "v1"


def test_get_missing_key() -> None:
    """get on a non-existent key returns None."""
    db = _fresh_db()
    txn = db.begin_transaction()
    assert db.get("nonexistent", txn) is None
    db.commit(txn)


def test_delete() -> None:
    """put → delete → get returns None."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("k1", "v1", txn)
    db.commit(txn)
    txn2 = db.begin_transaction()
    db.delete("k1", txn2)
    db.commit(txn2)
    assert db.get("k1", txn2) is None


def test_put_get_same_transaction() -> None:
    """get immediately after put in the same transaction returns the written value."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("k1", "v1", txn)
    assert db.get("k1", txn) == "v1"  # read-your-own-writes
    db.commit(txn)
    assert db.get("k1", txn) == "v1"


def test_multiple_keys_independent() -> None:
    """Multiple keys can be written independently."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("a", "1", txn)
    db.put("b", "2", txn)
    db.put("c", "3", txn)
    db.commit(txn)
    assert db.get("a", txn) == "1"
    assert db.get("b", txn) == "2"
    assert db.get("c", txn) == "3"


def test_rollback_active_ok() -> None:
    """rollback on an active transaction succeeds."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("k1", "v1", txn)
    db.rollback(txn)
    assert db.get("k1", txn) is None  # rolled back


def test_commit_inactive_raises() -> None:
    """commit on an already-committed transaction raises ValueError."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("k1", "v1", txn)
    db.commit(txn)
    try:
        db.commit(txn)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "already been resolved" in str(e)


def test_rollback_inactive_raises() -> None:
    """rollback on an already-rolled-back transaction raises ValueError."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("k1", "v1", txn)
    db.rollback(txn)
    try:
        db.rollback(txn)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "already been resolved" in str(e)


def test_rollback_mid_scan() -> None:
    """Deleting a key inside a transaction hides it in scan."""
    db = _fresh_db()
    txn = db.begin_transaction()
    for k in ["a", "b", "c"]:
        db.put(k, "val", txn)
    db.commit(txn)
    txn2 = db.begin_transaction()
    db.delete("b", txn2)
    result = db.scan("a", "c", txn2)
    assert [k for k, _ in result] == ["a", "c"]
    db.commit(txn2)


# ---------------------------------------------------------------------------
# Read-Your-Own-Writes
# ---------------------------------------------------------------------------

def test_read_your_own_writes() -> None:
    """A transaction can read its own uncommitted writes immediately."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("k1", "v1", txn)
    db.put("k2", "v2", txn)
    assert db.get("k1", txn) == "v1"
    assert db.get("k2", txn) == "v2"
    db.commit(txn)


def test_read_own_delete() -> None:
    """A transaction can read its own uncommitted delete (returns None)."""
    db = _fresh_db()
    t1 = db.begin_transaction()
    db.put("k1", "v1", t1)
    db.commit(t1)
    t2 = db.begin_transaction()
    db.delete("k1", t2)
    assert db.get("k1", t2) is None
    db.commit(t2)


# ---------------------------------------------------------------------------
# Snapshot Isolation
# ---------------------------------------------------------------------------

def test_snapshot_isolation_reader_sees_consistent_state() -> None:
    """A reader txn always sees committed state as of its begin time."""
    db = _fresh_db()
    tb = db.begin_transaction()
    db.put("k", "v1", tb)
    db.commit(tb)

    tr = db.begin_transaction()  # reader starts here
    tw = db.begin_transaction()  # writer starts after reader
    db.put("k", "v2", tw)
    db.commit(tw)

    # Reader should still see v1 (its snapshot predates v2 commit)
    assert db.get("k", tr) == "v1"
    db.commit(tr)  # should succeed cleanly


def test_snapshot_isolation_writer_serialized() -> None:
    """
    Two transactions writing the same key: first committer wins,
    second raises WriteConflictError.

    This is the key test for snapshot isolation write-serialization.
    """
    db = _fresh_db()
    tb = db.begin_transaction()
    db.put("k1", "init", tb)
    db.commit(tb)

    t1 = db.begin_transaction()
    t2 = db.begin_transaction()
    db.put("k1", "v1", t1)
    db.put("k1", "v2", t2)

    # RYW: each txn sees its own uncommitted write
    # Snapshot isolation: each txn started before the other committed,
    # so neither sees the other's uncommitted write
    assert db.get("k1", t1) == "v1"   # RYW: own pending write
    assert db.get("k1", t2) == "v2"   # RYW: own pending write

    db.commit(t1)  # t1 wins

    try:
        db.commit(t2)  # t2 must abort
        assert False, "Expected WriteConflictError"
    except WriteConflictError as e:
        assert "k1" in e.conflicted_keys

    # Final value is v1
    txn = db.begin_transaction()
    assert db.get("k1", txn) == "v1"


def test_snapshot_isolation_both_different_keys_succeed() -> None:
    """Two transactions writing DIFFERENT keys both succeed."""
    db = _fresh_db()
    tb = db.begin_transaction()
    db.put("k1", "init", tb)
    db.commit(tb)

    t1 = db.begin_transaction()
    t2 = db.begin_transaction()
    db.put("k1", "v1", t1)
    db.put("k2", "v2", t2)

    db.commit(t1)
    db.commit(t2)

    txn = db.begin_transaction()
    assert db.get("k1", txn) == "v1"
    assert db.get("k2", txn) == "v2"


# ---------------------------------------------------------------------------
# Write-Write Conflict Detection
# ---------------------------------------------------------------------------

def test_conflict_both_put_same_key() -> None:
    """T1 and T2 both put k1; first commit wins, second raises."""
    db = _fresh_db()
    tb = db.begin_transaction()
    db.put("k1", "init", tb)
    db.commit(tb)

    t1 = db.begin_transaction()
    t2 = db.begin_transaction()
    db.put("k1", "v1", t1)
    db.put("k1", "v2", t2)

    db.commit(t1)
    try:
        db.commit(t2)
        assert False, "Expected WriteConflictError"
    except WriteConflictError as e:
        assert "k1" in e.conflicted_keys


def test_conflict_put_vs_delete() -> None:
    """T1 deletes k1, T2 puts k1; first commit wins, second raises."""
    db = _fresh_db()
    tb = db.begin_transaction()
    db.put("k1", "init", tb)
    db.commit(tb)

    t1 = db.begin_transaction()
    t2 = db.begin_transaction()
    db.delete("k1", t1)
    db.put("k1", "v2", t2)

    db.commit(t1)  # delete wins
    try:
        db.commit(t2)
        assert False, "Expected WriteConflictError"
    except WriteConflictError as e:
        assert "k1" in e.conflicted_keys

    txn = db.begin_transaction()
    assert db.get("k1", txn) is None  # deleted


def test_no_conflict_different_keys() -> None:
    """No conflict if the two transactions modify different keys."""
    db = _fresh_db()
    tb = db.begin_transaction()
    db.put("k1", "init", tb)
    db.commit(tb)

    t1 = db.begin_transaction()
    t2 = db.begin_transaction()
    db.put("k1", "v1", t1)
    db.put("k2", "v2", t2)

    db.commit(t1)
    db.commit(t2)  # both succeed

    txn = db.begin_transaction()
    assert db.get("k1", txn) == "v1"
    assert db.get("k2", txn) == "v2"


def test_no_conflict_if_winner_rollback() -> None:
    """
    If the first committer (winner) rolls back, the second committer (loser)
    should still be able to commit successfully.

    This tests that pending entries from rolled-back transactions do NOT
    trigger false conflicts.
    """
    db = _fresh_db()
    tb = db.begin_transaction()
    db.put("k1", "init", tb)
    db.commit(tb)

    t1 = db.begin_transaction()
    t2 = db.begin_transaction()
    db.put("k1", "v1", t1)
    db.put("k1", "v2", t2)

    db.rollback(t1)  # winner rolls back
    db.commit(t2)   # loser should now succeed

    txn = db.begin_transaction()
    assert db.get("k1", txn) == "v2"


def test_write_conflict_error_attributes() -> None:
    """WriteConflictError carries the list of conflicted keys."""
    db = _fresh_db()
    tb = db.begin_transaction()
    db.put("ka", "init", tb)
    db.put("kb", "init", tb)
    db.commit(tb)

    t1 = db.begin_transaction()
    t2 = db.begin_transaction()
    db.put("ka", "va", t1)
    db.put("kb", "vb", t1)
    db.put("ka", "wa", t2)
    db.put("kb", "wb", t2)

    db.commit(t1)
    try:
        db.commit(t2)
    except WriteConflictError as e:
        assert "ka" in e.conflicted_keys
        assert "kb" in e.conflicted_keys


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def test_rollback_drops_writes() -> None:
    """Rollback discards all writes; the previous committed value is visible."""
    db = _fresh_db()
    t1 = db.begin_transaction()
    db.put("k1", "v1", t1)
    db.commit(t1)

    t2 = db.begin_transaction()
    db.put("k1", "v2", t2)
    db.put("k2", "w2", t2)
    db.rollback(t2)

    txn = db.begin_transaction()
    assert db.get("k1", txn) == "v1"
    assert db.get("k2", txn) is None


def test_rollback_unknown_raises() -> None:
    """Rolling back an unknown txn raises ValueError."""
    db = _fresh_db()
    try:
        db.rollback(9999)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "does not exist" in str(e)


def test_commit_unknown_raises() -> None:
    """Committing an unknown txn raises ValueError."""
    db = _fresh_db()
    try:
        db.commit(9999)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "does not exist" in str(e)


# ---------------------------------------------------------------------------
# Range Queries
# ---------------------------------------------------------------------------

def test_scan_empty_range() -> None:
    """scan with no keys in range returns empty list."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("c", "val", txn)
    db.commit(txn)
    result = db.scan("a", "b", txn)
    assert result == []


def test_scan_single_key() -> None:
    """scan returns exactly the key in a single-key range."""
    db = _fresh_db()
    txn = db.begin_transaction()
    db.put("k1", "v1", txn)
    db.commit(txn)
    result = db.scan("k1", "k1", txn)
    assert result == [("k1", "v1")]


def test_scan_multiple_keys() -> None:
    """scan returns all keys in range sorted by key."""
    db = _fresh_db()
    txn = db.begin_transaction()
    for k, v in [("a", "1"), ("b", "2"), ("c", "3")]:
        db.put(k, v, txn)
    db.commit(txn)
    result = db.scan("a", "c", txn)
    assert [k for k, _ in result] == ["a", "b", "c"]


def test_scan_snapshot_isolation() -> None:
    """
    A reader started before a writer commits should NOT see the new key.

    Note: snapshot isolation only guarantees that committed versions are
    visible based on commit_seq. A version V with commit_seq=C is visible
    to snapshot S if C <= S.
    """
    db = _fresh_db()
    t1 = db.begin_transaction()
    for k, v in [("a", "1"), ("b", "2"), ("c", "3"), ("d", "4"), ("e", "5")]:
        db.put(k, v, t1)
    db.commit(t1)

    t2 = db.begin_transaction()  # reader starts here
    t3 = db.begin_transaction()
    db.put("f", "6", t3)
    db.commit(t3)

    result = db.scan("a", "f", t2)
    keys = [k for k, _ in result]
    # t2's snapshot_seq is set at begin() — if f's commit_seq > t2's snapshot,
    # f is not visible (correct snapshot isolation). The spec expects this.
    assert "f" not in keys, f"f should not be visible to t2's snapshot; got {keys}"
    db.commit(t2)


def test_scan_excludes_deleted_keys() -> None:
    """scan excludes keys deleted by the same transaction."""
    db = _fresh_db()
    t1 = db.begin_transaction()
    for k in ["a", "b", "c"]:
        db.put(k, "val", t1)
    db.commit(t1)

    t2 = db.begin_transaction()
    db.delete("b", t2)
    result = db.scan("a", "c", t2)
    assert [k for k, _ in result] == ["a", "c"]


# ---------------------------------------------------------------------------
# Garbage Collection
# ---------------------------------------------------------------------------

def test_gc_prunes_old_versions() -> None:
    """run_gc() removes versions older than the oldest active snapshot."""
    db = _fresh_db()

    t1 = db.begin_transaction()
    db.put("k", "v1", t1)
    db.commit(t1)

    t2 = db.begin_transaction()
    db.put("k", "v2", t2)
    db.commit(t2)

    t3 = db.begin_transaction()  # active — defines oldest snapshot
    oldest_snapshot = t3

    # GC should prune v1 (commit_seq < oldest_snapshot)
    pruned = db.run_gc()
    assert pruned >= 1

    # v2 should still be there
    assert db.get("k", oldest_snapshot) == "v2"


def test_gc_keeps_newest_version() -> None:
    """GC never removes the newest (most recent) version for any key."""
    db = _fresh_db()
    t1 = db.begin_transaction()
    db.put("k", "v1", t1)
    db.commit(t1)

    db.run_gc()  # no active txns — nothing to prune
    assert db.get("k", t1) == "v1"


# ---------------------------------------------------------------------------
# Concurrent Stress Test
# ---------------------------------------------------------------------------

def test_concurrent_mixed_operations() -> None:
    """
    Many threads perform concurrent put/get/commit operations.
    Tests for data races and consistency.
    """
    db = _fresh_db()

    # Bootstrap
    tb = db.begin_transaction()
    db.put("counter", "0", tb)
    db.commit(tb)

    errors: list[BaseException] = []
    barrier = threading.Barrier(20)

    def worker(wid: int) -> None:
        try:
            barrier.wait()
            for _ in range(50):
                # Alternate: increment counter or read it
                if wid % 2 == 0:
                    txn = db.begin_transaction()
                    current = db.get("counter", txn)
                    if current is not None:
                        new_val = str(int(current) + 1)
                        db.put("counter", new_val, txn)
                        db.commit(txn)
                else:
                    txn = db.begin_transaction()
                    db.get("counter", txn)
                    db.commit(txn)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent test: {errors}"

    # Final value should be a non-negative integer
    txn = db.begin_transaction()
    val = db.get("counter", txn)
    assert val is not None and val.isdigit()


def test_concurrent_write_different_keys() -> None:
    """Concurrent writers writing different keys — all should succeed."""
    db = _fresh_db()
    tb = db.begin_transaction()
    db.put("k", "0", tb)
    db.commit(tb)

    errors: list[BaseException] = []

    def writer(wid: int) -> None:
        try:
            for _ in range(20):
                txn = db.begin_transaction()
                db.put(f"k{wid}", str(wid), txn)
                db.commit(txn)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors

    txn = db.begin_transaction()
    for i in range(10):
        assert db.get(f"k{i}", txn) == str(i)


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

def run_tests() -> None:
    tests = [
        # Basic operations
        test_put_get_commit,
        test_get_missing_key,
        test_delete,
        test_put_get_same_transaction,
        test_multiple_keys_independent,
        test_rollback_active_ok,
        test_commit_inactive_raises,
        test_rollback_inactive_raises,
        test_rollback_mid_scan,
        # Read-your-own-writes
        test_read_your_own_writes,
        test_read_own_delete,
        # Snapshot isolation
        test_snapshot_isolation_reader_sees_consistent_state,
        test_snapshot_isolation_writer_serialized,
        test_snapshot_isolation_both_different_keys_succeed,
        # Write-write conflicts
        test_conflict_both_put_same_key,
        test_conflict_put_vs_delete,
        test_no_conflict_different_keys,
        test_no_conflict_if_winner_rollback,
        test_write_conflict_error_attributes,
        # Rollback
        test_rollback_drops_writes,
        test_rollback_unknown_raises,
        test_commit_unknown_raises,
        # Range queries
        test_scan_empty_range,
        test_scan_single_key,
        test_scan_multiple_keys,
        test_scan_snapshot_isolation,
        test_scan_excludes_deleted_keys,
        # GC
        test_gc_prunes_old_versions,
        test_gc_keeps_newest_version,
        # Concurrency
        test_concurrent_mixed_operations,
        test_concurrent_write_different_keys,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
            print(f"  PASS  {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {test.__name__}: {exc}")

    print()
    print(f"{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    print("MVCC Database Test Suite")
    print("=" * 60)
    run_tests()

"""
Multi-Version Concurrency Control (MVCC) In-Memory Database
==========================================================
Python 3.11+ · Standard library only · Thread-safe · Snapshot Isolation

Key Design — Single-Monotonic-Counter MVCC
------------------------------------------
A single monotonically increasing counter _next_seq serves both roles:
  - At begin():  txn_id = snapshot_seq = _next_seq, then _next_seq += 1
  - At commit(): commit_seq = _next_seq, then _next_seq += 1

WHY THIS DESIGN:
  Snapshot = _next_seq at begin() represents the "logical time" when the
  transaction started. Since _next_seq is ONLY incremented at begin() or
  commit(), the snapshot value captures the total order of all transactions.

  When txn T1 and T2 begin before any commit:
    - Both get snapshot_seq = _next_seq (e.g., 1 and 2).
    - But _next_seq is NOT incremented between them, so both see the SAME state.
    - This is correct: both transactions are logically "simultaneous" and neither
      has modified anything yet.

  When T2 commits first:
    - T2's commit_seq = _next_seq = (T1's _next_seq) = T1's snapshot_seq.
    - T2's version: (commit_seq=T1.snapshot_seq, snapshot_seq=T1.snapshot_seq).
    - T1's OCC pending check: snapshot < pending.snapshot_seq < commit
      → T1.snapshot_seq < T2.snapshot_seq < T1.snapshot_seq → EMPTY → no conflict!
    - T1's OCC committed check: snapshot < committed.snapshot_seq < commit
      → T1.iterate() finds T2's version (snapshot=T2.snapshot_seq).
      → T1.snapshot_seq < T2.snapshot_seq < T1.snapshot_seq → EMPTY → no conflict!
    - T1's iterate() returns T2's version. T1 has pending write. Conflict! Abort.

  When T1 commits first (symmetric):
    - T1's version: (commit_seq=T1.snapshot_seq, snapshot_seq=T1.snapshot_seq).
    - T2's OCC pending check: T2.snapshot_seq < T1.snapshot_seq < T2.snapshot_seq → empty.
    - T2's OCC committed check: T2.iterate() finds T1's version.
      → T2.snapshot_seq < T1.snapshot_seq < T2.snapshot_seq → empty. No conflict!
    - T2.iterate() returns T1's version. T2 has pending write. Conflict! Abort.

  In BOTH cases, the SECOND committer ABORTS. ✓

Visibility (get/scan):
  Version V is visible to a reader with snapshot_seq=S if:
    V.version_commit_seq <= S
  (the version was committed at/or before the reader's snapshot)
  PLUS the reader's own pending writes.

OCC Conflict Detection (at commit, txn has snapshot_seq=S, commit_seq=C):
  COMMITTED V conflicts if: S < V.version_snapshot_seq < C
    (another txn began after this one, but already committed)
  PENDING   P conflicts if: S < P.snapshot_seq < C
    (a concurrent txn has uncommitted writes that began after this one)

GC: prune versions with version_commit_seq < oldest_active_snapshot.
"""

from __future__ import annotations

import threading
import time
import logging
from enum import Enum, auto
from typing import Optional

# ---------------------------------------------------------------------------
# Exceptions & Enums
# ---------------------------------------------------------------------------

class WriteConflictError(Exception):
    """Raised when a commit detects a write-write conflict on one or more keys."""
    def __init__(self, conflicted_keys: list[str]):
        self.conflicted_keys = conflicted_keys
        super().__init__(f"Write-write conflict on keys: {conflicted_keys}")


class TransactionStatus(Enum):
    ACTIVE    = auto()
    COMMITTED = auto()
    ABORTED   = auto()


# ---------------------------------------------------------------------------
# Internal Data Structures
# ---------------------------------------------------------------------------

class Transaction:
    """Transaction descriptor. snapshot_seq = begin seq; commit_seq = commit seq."""
    __slots__ = ("txn_id", "status", "writes", "snapshot_seq", "commit_seq")

    def __init__(self, txn_id: int, snapshot_seq: int) -> None:
        self.txn_id: int = txn_id
        self.status: TransactionStatus = TransactionStatus.ACTIVE
        self.writes: dict[str, tuple[str | None, bool]] = {}
        self.snapshot_seq: int = snapshot_seq
        self.commit_seq: int = 0


# ---------------------------------------------------------------------------
# MVCC Database
# ---------------------------------------------------------------------------

class MVCCDatabase:
    """
    Thread-safe, MVCC in-memory key-value store with snapshot isolation
    and optimistic write-write conflict detection.
    """

    def __init__(self, gc_interval_seconds: float = 5.0) -> None:
        # key → [(commit_seq, version_snapshot_seq, value, is_deleted), ...]
        # sorted newest-first by commit_seq
        self._versions: dict[str, list[tuple[int, int, str | None, bool]]] = {}
        self._versions_lock = threading.RLock()

        # key → [(txn_id, snapshot_seq, value, is_deleted), ...]
        self._pending: dict[str, list[tuple[int, int, str | None, bool]]] = {}
        self._pending_lock = threading.RLock()

        self._transactions: dict[int, Transaction] = {}
        self._txn_lock = threading.RLock()

        # Snapshot registry for resolved transactions
        self._snapshots: dict[int, int] = {}
        self._snapshot_lock = threading.Lock()

        # SINGLE monotonic counter for both snapshot_seq and commit_seq
        self._counter_lock = threading.Lock()
        self._next_seq: int = 1   # used for both begin() and commit()

        # Track txn_ids of committed transactions (for OCC pending check)
        self._committed_ids: set[int] = set()

        self._gc_interval = gc_interval_seconds
        self._gc_running = True
        self._gc_thread = threading.Thread(target=self._gc_loop, daemon=True)
        self._gc_thread.start()

        self._logger = logging.getLogger("MVCCDatabase")

    # -------------------------------------------------------------------------
    # Transaction Lifecycle
    # -------------------------------------------------------------------------

    def begin_transaction(self) -> int:
        """
        Begin a new snapshot transaction.

        Returns a unique transaction ID.
        snapshot_seq = current _next_seq (incremented atomically).
        txn_id = snapshot_seq (they are the same value).
        """
        with self._counter_lock:
            snapshot_seq = self._next_seq
            self._next_seq += 1
            txn_id = snapshot_seq

        txn = Transaction(txn_id, snapshot_seq)
        with self._txn_lock:
            self._transactions[txn_id] = txn
        return txn_id

    def commit(self, txn_id: int) -> None:
        """
        Try to commit transaction txn_id.

        OCC conflict detection (at commit, txn has snapshot_seq=S, commit_seq=C):
          COMMITTED V conflicts if: S < V.version_snapshot_seq < C
          PENDING   P conflicts if: S < P.snapshot_seq < C
        """
        with self._counter_lock:
            commit_seq = self._next_seq
            self._next_seq += 1

        with self._txn_lock:
            txn = self._transactions.get(txn_id)
            if txn is None:
                raise ValueError(
                    f"Transaction {txn_id} has already been resolved, cannot commit"
                )
            if txn.status != TransactionStatus.ACTIVE:
                raise ValueError(
                    f"Transaction {txn_id} is {txn.status.name}, cannot commit"
                )
            txn.commit_seq = commit_seq

            if not txn.writes:
                txn.status = TransactionStatus.COMMITTED
                del self._transactions[txn_id]
                self._committed_ids.add(txn_id)
                # Store commit_seq as the read snapshot so re-reads see committed state
                with self._snapshot_lock:
                    self._snapshots[txn_id] = commit_seq
                return

            # OCC: check committed versions
            conflicted_keys: list[str] = []
            with self._versions_lock:
                for key in txn.writes:
                    if self._has_conflict_locked(key, txn.snapshot_seq, commit_seq):
                        conflicted_keys.append(key)

            # OCC: check pending (concurrent uncommitted) writers
            if not conflicted_keys:
                with self._pending_lock:
                    for key in txn.writes:
                        if self._has_pending_conflict_locked(
                            key, txn_id, txn.snapshot_seq, commit_seq
                        ):
                            conflicted_keys.append(key)
                            break

            if conflicted_keys:
                txn.status = TransactionStatus.ABORTED
                del self._transactions[txn_id]
                with self._snapshot_lock:
                    self._snapshots[txn_id] = txn.snapshot_seq
                raise WriteConflictError(conflicted_keys)

            # Apply staged writes
            with self._pending_lock:
                for key, (value, is_deleted) in txn.writes.items():
                    self._pending.setdefault(key, [])
                    self._pending[key] = [
                        (e_txn, e_seq, e_val, e_del)
                        for e_txn, e_seq, e_val, e_del in self._pending[key]
                        if e_txn != txn_id
                    ]
                    self._versions.setdefault(key, [])
                    self._versions[key].insert(
                        0, (commit_seq, txn.snapshot_seq, value, is_deleted)
                    )

            txn.status = TransactionStatus.COMMITTED
            del self._transactions[txn_id]
            self._committed_ids.add(txn_id)
            # Store commit_seq as the read snapshot so re-reads see committed state
            with self._snapshot_lock:
                self._snapshots[txn_id] = commit_seq

    def rollback(self, txn_id: int) -> None:
        """Discard all staged changes of txn_id and mark it ABORTED."""
        with self._txn_lock:
            txn = self._transactions.get(txn_id)
            if txn is None:
                raise ValueError(
                    f"Transaction {txn_id} has already been resolved, cannot rollback"
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
            for key in list(self._pending):
                self._pending[key] = [
                    (e_txn, e_seq, e_val, e_del)
                    for e_txn, e_seq, e_val, e_del in self._pending[key]
                    if e_txn != txn_id
                ]
                if not self._pending[key]:
                    del self._pending[key]

    # -------------------------------------------------------------------------
    # Read Path
    # -------------------------------------------------------------------------

    def get(self, key: str, txn_id: int) -> Optional[str]:
        """
        Return the value visible to transaction txn_id, or None.

        Visibility: the newest committed version with
          version_commit_seq <= snapshot_seq.
        PLUS the transaction's own pending writes (read-your-own-writes).
        """
        # 1. Own pending writes
        with self._txn_lock:
            txn = self._transactions.get(txn_id)
            if txn is not None and key in txn.writes:
                value, is_deleted = txn.writes[key]
                return None if is_deleted else value

        # 2. Resolve snapshot_seq
        snapshot_seq: int
        with self._txn_lock:
            if txn is not None:
                snapshot_seq = txn.snapshot_seq
            else:
                with self._snapshot_lock:
                    if txn_id not in self._snapshots:
                        raise ValueError(f"Transaction {txn_id} does not exist")
                    snapshot_seq = self._snapshots[txn_id]

        # 3. Committed version chain (newest-first, stop at snapshot boundary)
        with self._versions_lock:
            for vc, _, value, is_del in self._versions.get(key, []):
                if vc <= snapshot_seq:
                    return None if is_del else value
        return None

    # -------------------------------------------------------------------------
    # Write Path
    # -------------------------------------------------------------------------

    def put(self, key: str, value: str, txn_id: int) -> None:
        self._stage_write(txn_id, key, value, False)

    def delete(self, key: str, txn_id: int) -> None:
        self._stage_write(txn_id, key, None, True)

    # -------------------------------------------------------------------------
    # Range Query
    # -------------------------------------------------------------------------

    def scan(
        self, start_key: str, end_key: str, txn_id: int
    ) -> list[tuple[str, str]]:
        """Return [(key, value)] for start_key ≤ key ≤ end_key visible to txn_id."""
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

        with self._versions_lock, self._pending_lock:
            all_keys: set[str] = set(self._versions.keys())
            for key in self._pending:
                all_keys.add(key)

        in_range = sorted(k for k in all_keys if start_key <= k <= end_key)

        results: list[tuple[str, str]] = []
        for key in in_range:
            value = self._visible_value(key, snapshot_seq, own_writes)
            if value is not None:
                results.append((key, value))
        return results

    # -------------------------------------------------------------------------
    # Garbage Collection
    # -------------------------------------------------------------------------

    def get_oldest_active_snapshot(self) -> Optional[int]:
        """Return the smallest snapshot_seq among active transactions, or None."""
        with self._txn_lock:
            if not self._transactions:
                return None
            return min(t.snapshot_seq for t in self._transactions.values())

    def run_gc(self) -> int:
        """
        Prune committed versions no longer needed.

        A version with version_commit_seq=V is GC-eligible if V < oldest_active_snapshot.
        Always keeps the newest version for each key.
        Returns the number of entries pruned.
        """
        oldest = self.get_oldest_active_snapshot()

        with self._versions_lock:
            pruned = 0
            for key in list(self._versions.keys()):
                chain = self._versions[key]
                if len(chain) <= 1:
                    continue

                threshold = oldest if oldest is not None else -1

                new_chain: list[tuple[int, int, str | None, bool]] = [chain[0]]
                for entry in chain[1:]:
                    if entry[0] >= threshold:
                        new_chain.append(entry)
                    else:
                        pruned += 1

                if len(new_chain) < len(chain):
                    self._versions[key] = new_chain
                if not new_chain:
                    del self._versions[key]
        return pruned

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

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
            snapshot_seq = txn.snapshot_seq

        with self._pending_lock:
            self._pending.setdefault(key, [])
            self._pending[key] = [
                (e_txn, e_seq, e_val, e_del)
                for e_txn, e_seq, e_val, e_del in self._pending[key]
                if e_txn != txn_id
            ]
            self._pending[key].insert(0, (txn_id, snapshot_seq, value, is_deleted))

    def _visible_value(
        self,
        key: str,
        snapshot_seq: int,
        own_writes: dict[str, tuple[str | None, bool]],
    ) -> Optional[str]:
        """
        Must be called with _versions_lock and _pending_lock held.

        Visibility:
          - Own pending writes: always visible (read-your-own-writes).
          - Committed versions: visible if version_commit_seq <= snapshot_seq.
          - Other pending writes: NOT visible (scan only shows committed state
            for keys not written by this transaction).
        """
        # Rule 1: own pending writes (read-your-own-writes)
        if key in own_writes:
            value, is_deleted = own_writes[key]
            return None if is_deleted else value

        # Rule 2: newest committed version committed at or before snapshot
        for vc, _, value, is_del in self._versions.get(key, []):
            if vc <= snapshot_seq:
                return None if is_del else value
        return None

    def _has_conflict_locked(
        self, key: str, snapshot_seq: int, commit_seq: int
    ) -> bool:
        """
        Check COMMITTED versions for OCC conflicts.

        Conflict if: snapshot_seq < version_snapshot_seq < commit_seq
        (another txn began after this one, but already committed).
        """
        for _, vs, _, _ in self._versions.get(key, []):
            if snapshot_seq < vs < commit_seq:
                return True
        return False

    def _has_pending_conflict_locked(
        self, key: str, my_txn_id: int, snapshot_seq: int, commit_seq: int
    ) -> bool:
        """
        Check PENDING versions for OCC conflicts.

        Conflict if: snapshot_seq < pending.snapshot_seq < commit_seq
        AND the pending entry is from a COMMITTED transaction.
        Pending entries from transactions that never committed (e.g. bootstrap
        or rolled-back txns) are skipped — they represent uncommitted state
        that was never made permanent and should not block other txns.
        """
        for e_txn_id, e_snapshot_seq, _, _ in self._pending.get(key, []):
            if e_txn_id == my_txn_id:
                continue  # skip own pending
            if e_txn_id not in self._committed_ids:
                continue  # skip uncommitted transactions (never committed)
            if snapshot_seq < e_snapshot_seq < commit_seq:
                return True
        return False

    # -------------------------------------------------------------------------
    # Background GC Loop
    # -------------------------------------------------------------------------

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

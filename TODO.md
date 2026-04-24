# TODO.md — Task Registry

## Format
- [ ] TASK | Priority | Created | Due | Dependencies

## Priority Levels
- P0: Critical — Do now, interrupt anything
- P1: High — Do today
- P2: Medium — Do this week
- P3: Low — Do when idle

## Task State Machine
```
PENDING → ACTIVE → COMPLETED → ARCHIVED
              ↓
           BLOCKED → (waiting on dependency)
              ↓
           PENDING
              
ACTIVE → FAILED → PENDING (retry)
ACTIVE → CANCELLED → ARCHIVED
```

---

## P0 (Critical)
_No items_

---

## P1 (High — Today)

---

## P2 (Medium — This Week)

---

## P3 (Low — When Idle)

---

## Blocked
_No items_

---

## Completed (Last 7 Days)
_No items completed this week_

---

## Cancelled
_No items cancelled_

---

_Last updated: 2026-04-24 by JARVIS (100× Autonomous Agent)_
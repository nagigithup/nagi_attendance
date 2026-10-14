# Phase 10 release hardening and UAT

Date: 2026-10-14

## Release gates

| Area | Result | Evidence |
|---|---|---|
| Late approval | PASS | Decisions are saved with actor/time and Version audit. Submitted Attendance is read-only to this feature. The report flags late decisions for controlled HR review. |
| Worked-time overlap | PASS | Approved intervals are unioned, clipped to scheduled shift time, and reduced by HRMS-valid worked intervals before threshold credit. |
| Working-hours separation | PASS | Native `Attendance.working_hours` is returned unchanged; report columns separate actual, approved, creditable, and compliance hours. |
| Leave/payroll/overtime isolation | PASS | Workflow test confirms no Leave Application is created. No payroll/overtime document is read or written. Creditable hours affect only status thresholds and covered late/early flags. |
| Feature gate | PASS | Disabled companies cannot submit through APIs, do not see the employee UI, and do not query permission exemptions. |
| Audit trail | PASS | Approval, rejection, and cancellation use validated Document saves and store decision/cancellation actor and timestamp. Notifications and Versions are tested. |
| Authorization | PASS | Employee, assigned manager, HR Manager, and Administrator access passed; unrelated employee read/approval attempts were rejected. |

## Sanitized staging comparison

An isolated local site, `nagi-phase10-staging.localhost`, was restored from a local customer backup and identifiers were replaced with invalid/example identities before validation. The scheduler remained disabled. No production system was contacted.

Before and after `bench migrate`, table checksums and row counts were identical for:

- Nagi Attendance Settings: 1
- User Permission: 8
- Custom Field: 177
- Property Setter: 188
- Custom DocPerm: 496
- Has Role assignments
- Workflows and workflow child tables: 0
- Workspaces: 32
- Attendance: 0

The Short Permission activation value remained `0`. Metadata synchronization introduced no changes in those customer-owned/configuration tables. Application-owned DocType and report metadata changed as expected for v1.1.0.

## UAT identities

- Employee: submitted, viewed, and cancelled own requests.
- Department manager/assigned approver: received notification and approved/rejected assigned requests.
- HR administrator: could view history under the HR Manager authorization policy.
- System administrator: could view configuration and historical records.
- Unrelated employee: could neither read nor approve another employee's request.

All UAT writes ran inside the Frappe integration-test transaction and rolled back. The ADAN feature flag remained disabled and no permission test records remained.

## Rollback readiness

Rollback is documented in `RELEASE_1.1.0.md`. Disabling the per-company flag stops new submissions and compliance credits without deleting history. Code rollback retains the DocType/table. Database rollback requires the pre-upgrade full backup and transaction reconciliation.

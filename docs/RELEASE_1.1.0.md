# Nagi Attendance v1.1.0

## Release scope

Version 1.1.0 adds company-scoped Short Permission (طلب إذن أثناء الدوام). The feature is disabled by default on fresh and upgraded sites. It has no effect on request APIs, employee navigation, or attendance calculations until an authorized administrator enables `Enable Short Permission` on that company's `Nagi Attendance Settings` record.

No install or migration hook creates or updates company settings. Frappe schema synchronization adds new fields with schema defaults only; it does not reset existing rows. The release contains no Company, Department, Employee, manager, approver, attendance, check-in, user permission, or customer workflow fixture.

## Upgrade procedure

1. Take a full site backup including public and private files and retain the currently deployed app revision.
2. In a staging copy, install the 1.1.0 code and run `bench --site <site> migrate`.
3. Run `bench build --app nagi_attendance` and clear the site cache.
4. Verify existing company settings, department settings, Employee approvers, User Permissions, Attendance, Employee Checkin, and any existing permission records against the pre-upgrade snapshot.
5. Confirm Short Permission is disabled for every company unless an administrator had explicitly set a value.
6. Run the automated app tests and complete employee/manager acceptance testing for one enabled company and one disabled company.
7. Deploy the same tested revision through the Frappe Cloud private-bench update flow. Do not copy the development database to production.

Running `bench migrate` repeatedly is supported: this release has no data-seeding patch and no migration routine that writes company settings or business records.

## Activation

An HR Manager or System Manager creates/opens `Nagi Attendance Settings` for the target Company, reviews all Short Permission policy fields, and enables the checkbox. Activation is independent for each company. Disabling it later blocks employee API/UI actions and stops exemptions while preserving configuration and historical records for administrators.

Approved permission contributes only to attendance status thresholds and covered late/early flags when `Permission Counted as Authorized Working Time` is enabled. The native Attendance `working_hours` value remains actual worked time. Authorized duration is stored and reported separately. No Leave Application or leave ledger entry is created.

Authorized compliance hours exclude any part of a permission interval already covered by valid worked-time intervals. They are used only while deciding attendance thresholds and never replace native working hours or feed overtime/payroll calculations.

## Late approval and controlled correction

Approving a request after a submitted Attendance record does not amend or cancel that Attendance. The Short Permission Register immediately shows the approved interval, creditable authorized hours, actual worked hours, combined compliance hours, decision timestamp, and `Review Required` when the decision occurred after the submitted Attendance was last modified.

If the native Attendance status must be corrected, an authorized HR administrator must:

1. Review the submitted Attendance, linked Employee Checkins, shift, permission decision history, and report calculation.
2. Record the reason and obtain the organization's required approval outside or in the standard HR workflow.
3. Use ERPNext's supported cancel/amend or attendance reconciliation procedure. Never update submitted Attendance with SQL or `db_set`.
4. Re-run normal attendance processing only where HRMS permits it, verify actual and authorized hours separately, and retain the amended-document and Version audit trails.

The application deliberately provides no API that rewrites submitted Attendance records.

## Rollback

1. Disable Short Permission for affected companies to stop new requests and exemptions immediately.
2. Restore the previously deployed application revision and rebuild assets.
3. Run `bench --site <site> migrate` and clear cache. Frappe normally retains the new DocType/table and columns; retaining them safely preserves request history.
4. If a full database rollback is required, restore the pre-upgrade full backup during the approved maintenance window. This loses transactions created after that backup, so reconcile them before proceeding.

Never delete the permission table or fields as part of an application-code rollback. Do not amend submitted Attendance records automatically.

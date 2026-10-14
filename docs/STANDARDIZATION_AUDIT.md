# Standardization and upgrade-safety audit

| Area | Finding | v1.1.0 treatment |
|---|---|---|
| Runtime Python and Vue | Company context is resolved from the authenticated Employee; no runtime company-name branch exists. | Retained and reused for Short Permission. |
| Company settings | One `Nagi Attendance Settings` document per Company; missing records use safe runtime defaults. | Added disabled-by-default policy fields; no migration writes existing rows. |
| ADAN provisioning | `setup/adan_law_firm.py` contained a full customer seed (company, departments, users, employees, shifts, location and policies). | Removed from the distributable application. Existing database records are untouched. |
| Legacy ADAN patch | One patch imported the customer seed constants and created ADAN settings. | Removed from `patches.txt` and source. Previously migrated customer data is retained. |
| ADAN tests/docs | Tests and operational documentation referenced real customer identities and policy. | Seed test removed. This audit records the legacy boundary without packaging defaults. |
| Attendance policy | Generic company flag suppresses no-log absence generation; native HRMS handles real check-ins. | Retained. Short Permission adds only an enabled-company threshold adjustment. |
| Departments | Runtime filtering is passed as a Department link and default is company-validated. | No hardcoded department is used by runtime or new feature. |
| Managers/approvers | Native Employee `leave_approver` and `reports_to` relationships are customer data. | Resolved at request creation; never seeded or reset. |
| Fixtures | No `fixtures` hook is configured. Standard DocTypes, Page/sidebar/dock metadata and reports sync as app definitions. | No customer-owned records, singleton settings, workflows, scripts, or User Permissions exported. |
| Install/migrate hooks | No active `after_install` or `after_migrate` hook. | Kept hook-free; repeated migration is idempotent. |
| Site-resident customizations | ADAN may contain Custom Fields, Property Setters, workflows, roles and records not represented by source. | Must be snapshot-compared during staging upgrade; this release does not write them. Metadata name collisions remain a normal Frappe sync risk. |

## Metadata ownership rule

Application-owned DocType schemas, reports, navigation metadata, roles declared on those DocTypes, translations, and logic may be synchronized by Frappe. Customer-owned values and business documents are never fixtures. If a customer needs to alter an application-owned field or role permission, use a separately named Custom Field/Permission Manager customization and regression-test it because Frappe schema synchronization can reconcile standard metadata.

# Adan Law Firm — Local HRMS Implementation

## Scope and isolation

- Local site: `adan.local`
- Installed applications: Frappe, ERPNext, HRMS, and Nagi Attendance
- Company: `أدن للمحاماة والاستشارات القانونية`
- Country/currency/time zone: Saudi Arabia / SAR / Asia-Riyadh
- This setup does not alter the cloud site or any other local site.

The idempotent setup entry point is:

```bash
bench --site adan.local execute nagi_attendance.setup.adan_law_firm.execute
```

## Implemented configuration

- Arabic system language, Sunday as the first day of the week, and 24-hour time.
- Friday/Saturday weekly holidays for 2026.
- Confirmed fixed Saudi holidays: Founding Day (22 February) and National Day (23 September).
- The lunar Eid holidays are intentionally not hard-coded until the official/company calendar is confirmed.
- Confirmed office: `شركة أدان للمحاماة | ADAN LAW FIRM`.
- Address: `شارع بحر العرب، الخليج، الرياض 13224، المملكة العربية السعودية`.
- Google Maps source: <https://maps.app.goo.gl/HuDpLxp7xA95nw889?g_st=ic>.
- Office shift location at `24.7870341, 46.8051581` with a 100-metre local test radius.
- Office shifts 09:00–15:00 and 09:00–16:00, with 30-minute check-in/check-out windows.
- Native HRMS mobile check-in and server-side geofence enforcement. A custom app validation hook closes the HRMS v16 off-shift gap by enforcing the active Shift Assignment location even when HRMS cannot resolve a shift outside its processing window.
- Attendance go-live date: 7 October 2026. Shift processing and the three active Shift Assignments begin on that date; Employee joining dates remain separate and unchanged.
- Auto Attendance remains enabled for real Employee Checkin logs. Native Present, working-hours, and late-entry processing is preserved, while a company-scoped `Shift Type` extension suppresses automatic Absent creation for Adan employees who have no check-in data.
- Late entry is enabled with a 10-minute grace period; early-exit, half-day, and absence thresholds remain disabled pending policy approval.
- Five active male Employee records and Arabic user accounts with least-privilege HR roles. No employee was granted System Manager.
- Osama has HR Manager and Leave Approver roles. Abdulrahman Al-Sulami is Osama's approver; Osama is the approver for Abdulrahman Al-Sulami and the three staff members.
- Arabic departments are assigned: `الإدارة` for the partners and `الإدارة القانونية` for the three staff members.
- The three staff members have submitted active shift assignments starting 7 October 2026. The partners intentionally have no shift assignment.
- The 2026 holiday list is linked through a submitted company Holiday List Assignment.
- Draft 2026 leave policy and statutory leave types; no leave balances have been allocated while joining dates remain provisional.
- Provisional DOB and joining-date flags are deployment-managed Employee custom fields.

## Confirmed employee defaults

The final implementation instruction confirms all five employees as Male. The requested provisional values are stored as:

- Date of birth: 1990-01-01
- Date of joining: 2026-01-01

Both dates are explicitly flagged as provisional on every Employee and must be replaced from verified HR records before balances or payroll-dependent rules are activated.

Also confirm before production use:

- Actual dates of birth and joining; current placeholders are flagged as provisional.
- Production approval of the 100-metre geofence radius.
- Whether early-exit, half-day, and absence thresholds should be enabled.
- Annual-leave carry-forward rules and approved handling of the 30-day entitlement after five consecutive years.
- Payroll handling for statutory sick-leave pay tiers; the Leave Type permits up to 120 days but does not attempt to calculate the pay tiers.
- Supporting-document and eligibility rules for event, Hajj, examination, and maternity leave.
- Official Eid dates/company calendar before adding those holidays.

## Acceptance checks

1. Log in as each employee and test IN and OUT within the office radius.
2. Confirm the same action is rejected outside the radius.
3. Run automatic attendance after the shift's permitted checkout window.
4. Submit leave as each non-manager employee and verify only Osama can approve it.
5. Submit Osama's leave to the separately confirmed approver.
6. Verify the Manager Attendance dashboard with Osama and confirm a regular employee cannot access manager-only data.
7. Confirm Arabic/RTL rendering on desktop and mobile.

## Cloud migration checklist

1. Resolve the remaining production inputs above and repeat the acceptance tests on `adan.local`.
2. Change the local Administrator password from its temporary setup value.
3. Ensure the same compatible app versions/branches exist on the Frappe Cloud private bench.
4. Deploy application code containing this setup and the Nagi Attendance fixtures/assets.
5. Create and validate a fresh local full backup with database, public files, private files, and site configuration.
6. Before the manual restore, take and retain a fresh full backup of the existing Frappe Cloud site.
7. During a maintenance window, use Frappe Cloud's supported **Restore with Files** workflow on the confirmed Adan production site.
8. Trigger migration and required asset rebuilding through supported Private Bench controls, then clear the site cache.
9. Repeat the acceptance checks above and verify HTTPS, email, scheduler, roles, and mobile location permissions.
10. Retain both pre-restore backups and document the rollback window.

Do not copy only database rows for this implementation: the custom app code, fixtures, assets, and site files are part of the deployment.

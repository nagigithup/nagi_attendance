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
- Native HRMS mobile check-in and server-side geofence enforcement.
- Auto Attendance enabled; late-entry, early-exit, half-day, and absence thresholds remain disabled pending policy confirmation.
- Five Arabic user accounts with least-privilege HR roles. No employee was granted System Manager.
- Osama has HR Manager and Leave Approver roles; the other four users point to him as their leave approver once Employee records are created.
- Draft 2026 leave policy and leave types; no leave balances have been allocated.
- Provisional DOB and joining-date flags are deployment-managed Employee custom fields.

## Required inputs before Employee creation

HRMS requires a Gender value. The setup deliberately refuses to invent it. After the five official values are supplied, run:

```bash
bench --site adan.local execute nagi_attendance.setup.adan_law_firm.execute \
  --kwargs '{"genders":{"osama@adanlawfirm.com":"<Gender>","abdulrahman@adanlawfirm.com":"<Gender>","a.mohsen@adanlawfirm.com":"<Gender>","mohammed@adanlawfirm.com":"<Gender>","othman@adanlawfirm.com":"<Gender>"}}'
```

Also confirm before production use:

- Osama's own leave approver (self-approval is blocked).
- Actual dates of birth and joining; current requested placeholders are flagged as provisional.
- Department assignments.
- Production geofence radius.
- Late arrival, early exit, half-day, and absence thresholds.
- Leave carry-forward, sick-pay tiers, maternity eligibility, and company-specific allocation rules.
- Official Eid dates/company calendar before adding those holidays.

## Acceptance checks

After completing the Employee records:

1. Log in as each employee and test IN and OUT within the office radius.
2. Confirm the same action is rejected outside the radius.
3. Run automatic attendance after the shift's permitted checkout window.
4. Submit leave as each non-manager employee and verify only Osama can approve it.
5. Submit Osama's leave to the separately confirmed approver.
6. Verify the Manager Attendance dashboard with Osama and confirm a regular employee cannot access manager-only data.
7. Confirm Arabic/RTL rendering on desktop and mobile.

## Cloud migration checklist

1. Complete the missing inputs and acceptance tests on `adan.local`.
2. Change the local Administrator password from its temporary setup value.
3. Ensure the same compatible app versions/branches exist on the Frappe Cloud private bench.
4. Deploy application code containing this setup and the Nagi Attendance fixtures/assets.
5. Take a fresh encrypted full backup with database, public files, and private files.
6. Restore first into a staging site, not the production site.
7. Run `bench --site <staging-site> migrate`, rebuild assets, and clear cache.
8. Repeat the acceptance checks above and verify email, scheduler, roles, and mobile location permissions.
9. Schedule a production maintenance window, take a new source backup, restore it, migrate, and smoke-test.
10. Retain the pre-migration backup and a documented rollback window.

Do not copy only database rows for this implementation: the custom app code, fixtures, assets, and site files are part of the deployment.

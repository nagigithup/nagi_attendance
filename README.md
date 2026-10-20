# Nagi Attendance & Leave

Arabic-first, white-label Attendance and Leave PWA for Frappe HR v16. The app uses native Employee Checkin, Attendance, shifts, holidays, Leave Application, allocations, and workflow records. It does not implement a parallel HR backend.

## Features

- Employee PWA at `/attendance`, with Arabic RTL and English LTR
- Server-authoritative check-in/out and company/shift-location geofencing
- Personal attendance status and history
- Native leave balances, requests, history, cancellation, and manager actions
- Company-scoped Short Permission requests and approval, disabled by default
- Company logo, name, currency, timezone, language, and brand color
- Multi-company selector only for companies linked to the authenticated user
- Existing manager dashboard at `/desk/manager-attendance`
- Neutral install identity for safe use on multi-company sites

## Install

```bash
bench get-app <your-nagi-attendance-repository>
bench --site your-site install-app nagi_attendance
bench --site your-site migrate
bench build --app nagi_attendance
```

Requirements: Frappe/ERPNext v16 and Frappe HR v16. Production PWA installation and browser geolocation require HTTPS.

## Required customer setup

1. Configure each `Company`, including its logo and default currency.
2. Link every mobile user to an active `Employee` through `user_id`.
3. Configure Holiday Lists, Shift Types, and submitted Shift Assignments in HRMS.
4. Configure Shift Locations (coordinates and radius) and assign them to shifts/employees.
5. In HR Settings, enable mobile employee check-in. Enable geolocation tracking when required.
6. Create one `Nagi Attendance Settings` record per Company. Set feature switches, brand color, start date, GPS policy, and optional additional Shift Locations.
7. Configure Leave Periods, Leave Types, policies/allocations, and employee/department Leave Approvers.
8. Configure a Leave Application Workflow if the customer needs approval states beyond native approve/reject.
9. Assign standard HRMS roles and User Permissions. Ordinary employees must not receive HR Manager access.
10. Open `/attendance`; use the browser's Add to Home Screen / Install command.

Without a Nagi settings record, safe product defaults enable the existing two mobile modules but do not enable GPS, no-log absence suppression, or Short Permission. Shift, leave, and permission policy setup is never synthesized.

## Company policy and security

The browser never chooses an arbitrary employee. Every employee/company context is resolved from the authenticated session user. A company selector is returned only for active Employee records linked to that same user. Check-in time comes from the server, and Employee Checkin validation runs server-side. Writes never use `ignore_permissions=True`.

`Nagi Attendance Settings` is editable only by System Manager and HR Manager. Native Frappe permissions and HRMS workflow transitions remain authoritative for leave creation, cancellation, and approval.

## PWA behavior

Production builds emit content-hashed JavaScript and CSS plus `asset-manifest.json`. The attendance page is always served with no-cache headers and resolves the current hashes from that manifest. The service worker caches only the matching versioned application shell, removes only older Nagi Attendance caches after activation, and offers a bilingual update prompt before activating a waiting worker. API responses, employee images/files, page navigations, and attendance, leave, or permission data are network-only with `no-store`; check-ins are never queued offline.

Browsers generally cache manifest metadata outside the signed-in employee context. To avoid leaking or pinning one company's identity on multi-company sites, the install manifest uses the neutral **Nagi Attendance & Leave** name and icon. In-app identity is always company-specific.

## Development

The Vue 3 source is under `frontend/`. HRMS is a required app, so the local build reuses its installed Vite/Vue toolchain:

```bash
cd apps/nagi_attendance/frontend
../../hrms/frontend/node_modules/.bin/vite build
cd ../../..
bench build --app nagi_attendance
bench --site your-site clear-cache
bench --site your-site clear-website-cache
```

Run the Vite command before `bench build`; it generates the hashed assets, manifest, and deployment-specific service worker used by `/attendance`.

Run tests with:

```bash
bench --site your-site run-tests --app nagi_attendance
```

No customer provisioning data or customer-specific defaults are shipped by the application. Existing site data is managed independently and is never rewritten by installation or migration hooks.

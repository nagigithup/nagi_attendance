# Nagi Attendance

Nagi Attendance is a manager-focused Attendance & Leave dashboard for Frappe HR. It reads the standard HRMS records and does not create a parallel attendance model.

## Requirements

- Frappe / ERPNext v16
- Frappe HR (`hrms`) v16
- A user with read access to Employee, Attendance, Employee Checkin, Leave Application, and Holiday List
- `HR Manager`, `HR User`, or `System Manager` to see the standard Desk page/workspace

## Install

```bash
bench --site your-site install-app hrms
bench --site your-site install-app nagi_attendance
bench --site your-site migrate
bench build --app nagi_attendance
```

Open **Nagi Attendance** from Desk or visit `/app/manager-attendance`.

## APIs

- `nagi_attendance.api.get_today_dashboard(date=None, employee=None, department=None)`
- `nagi_attendance.api.get_monthly_attendance(year, month, employee=None, department=None)`
- `nagi_attendance.api.get_leave_dashboard(date=None)`
- `nagi_attendance.api.get_employee_details(employee, date=None, year=None, month=None)`
- `nagi_attendance.api.apply_leave_action(name, action)`

All list queries use the current user's Frappe permissions. Leave decisions are restricted to currently available workflow transitions and go through Frappe's workflow engine.

## Status precedence

1. Submitted, approved Leave Application covering the date
2. Holiday or weekly off from the employee/company Holiday List Assignment
3. Submitted Attendance status
4. Same-day Employee Checkin status for a near-real-time view
5. Absent for unrecorded past working days, or Not Checked In for today

Attendance remains authoritative for hours, late entry, early exit, and check-in/out times once it exists. Before auto-attendance is processed, check-ins supply the live status and paired working time.

## Tests

```bash
bench --site your-site run-tests --app nagi_attendance
```

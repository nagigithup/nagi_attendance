import { computed, ref } from "vue"

const messages = {
	ar: {
		home:"الرئيسية", attendance:"الحضور", leave:"الإجازات", account:"حسابي", hello:"مرحباً",
		today:"اليوم", shift:"الوردية", noShift:"لا توجد وردية معيّنة", checkIn:"تسجيل الحضور", checkOut:"تسجيل الانصراف",
		lastActivity:"آخر حركة", notChecked:"لم يتم تسجيل الحضور", checkedIn:"تم تسجيل الحضور", present:"حاضر", absent:"غائب",
		late:"متأخر", onLeave:"في إجازة", workingHours:"ساعات العمل", upcomingLeave:"الإجازة القادمة",
		leaveBalance:"رصيد الإجازات", pendingRequests:"طلبات قيد الانتظار", managerApprovals:"طلبات تحتاج موافقتك",
		noUpcoming:"لا توجد إجازات معتمدة قادمة.", noBalance:"لا توجد أرصدة إجازات سارية.", noPending:"لا توجد طلبات معلقة.",
		monthlyHistory:"سجل الحضور", checkinActivity:"حركات الحضور والانصراف", dailyAttendance:"الحضور اليومي المحتسب", outsideShift:"خارج الوردية", noAttendance:"لا توجد سجلات حضور لهذه الفترة.", requestLeave:"طلب إجازة",
		leaveType:"نوع الإجازة", fromDate:"من تاريخ", toDate:"إلى تاريخ", halfDay:"نصف يوم", reason:"السبب",
		submit:"إرسال الطلب", history:"السجل", approve:"موافقة", reject:"رفض", processing:"جارٍ التنفيذ…", cancel:"إلغاء الطلب", days:"أيام",
		profile:"الملف الشخصي", employeeId:"رقم الموظف", department:"القسم", designation:"المسمى الوظيفي", company:"الشركة",
		language:"اللغة", arabic:"العربية", english:"English", logout:"تسجيل الخروج", loading:"جارٍ التحميل…", refresh:"تحديث",
		location:"الموقع", locating:"جارٍ تحديد موقعك…", locationRequired:"يجب السماح بالوصول إلى الموقع لتسجيل الحضور.",
		locationInaccurate:"دقة الموقع منخفضة. انتظر قليلاً ثم حاول مجدداً.", confirmAction:"تأكيد العملية؟", success:"تمت العملية بنجاح.",
		error:"تعذر إكمال العملية.", settingsMissing:"إعدادات الإجازات غير مكتملة. يرجى التواصل مع مسؤول الموارد البشرية.",
		attendanceDisabled:"الحضور عبر الجوال غير مفعّل لهذه الشركة.", leaveDisabled:"طلبات الإجازة عبر الجوال غير مفعّلة لهذه الشركة.",
		open:"مفتوح", approved:"معتمد", rejected:"مرفوض", cancelled:"ملغي", refreshChanged:"تم تحديث البيانات.",
		select:"اختر", employee:"الموظف", duration:"المدة", accuracy:"الدقة", meters:"متر", switchCompany:"تغيير الشركة",
		permission:"طلب إذن", shortPermission:"طلب إذن أثناء الدوام", requestPermission:"طلب إذن", myRequests:"طلباتي", pendingPermissionApprovals:"طلبات بانتظار الموافقة", permissionDate:"تاريخ الإذن", permissionType:"نوع الإذن", lateArrival:"تأخر في الحضور", earlyDeparture:"انصراف مبكر", temporaryExit:"خروج مؤقت", fromTime:"من الساعة", toTime:"إلى الساعة", permissionReason:"سبب الإذن", hours:"ساعات", authorizedDuration:"المدة المصرح بها",
	},
	en: {
		home:"Home", attendance:"Attendance", leave:"Leave", account:"My Account", hello:"Hello",
		today:"Today", shift:"Shift", noShift:"No shift assigned", checkIn:"Check In", checkOut:"Check Out",
		lastActivity:"Last activity", notChecked:"Not checked in", checkedIn:"Checked in", present:"Present", absent:"Absent",
		late:"Late", onLeave:"On Leave", workingHours:"Working hours", upcomingLeave:"Upcoming leave",
		leaveBalance:"Leave balance", pendingRequests:"Pending requests", managerApprovals:"Requests awaiting your approval",
		noUpcoming:"No upcoming approved leave.", noBalance:"No valid leave allocations.", noPending:"No pending requests.",
		monthlyHistory:"Attendance history", checkinActivity:"Check-in activity", dailyAttendance:"Calculated daily attendance", outsideShift:"Outside shift", noAttendance:"No attendance records for this period.", requestLeave:"Request leave",
		leaveType:"Leave type", fromDate:"From date", toDate:"To date", halfDay:"Half day", reason:"Reason",
		submit:"Submit request", history:"History", approve:"Approve", reject:"Reject", processing:"Processing…", cancel:"Cancel request", days:"days",
		profile:"Profile", employeeId:"Employee ID", department:"Department", designation:"Designation", company:"Company",
		language:"Language", arabic:"العربية", english:"English", logout:"Log out", loading:"Loading…", refresh:"Refresh",
		location:"Location", locating:"Finding your location…", locationRequired:"Location permission is required to record attendance.",
		locationInaccurate:"Location accuracy is low. Wait a moment and try again.", confirmAction:"Confirm this action?", success:"Completed successfully.",
		error:"Unable to complete the action.", settingsMissing:"Leave setup is incomplete. Please contact HR.",
		attendanceDisabled:"Mobile attendance is disabled for this company.", leaveDisabled:"Mobile leave is disabled for this company.",
		open:"Open", approved:"Approved", rejected:"Rejected", cancelled:"Cancelled", refreshChanged:"Data refreshed.",
		select:"Select", employee:"Employee", duration:"Duration", accuracy:"Accuracy", meters:"m", switchCompany:"Switch company",
		permission:"Permission", shortPermission:"Permission During Working Hours", requestPermission:"Request Permission", myRequests:"My Requests", pendingPermissionApprovals:"Pending Approvals", permissionDate:"Permission date", permissionType:"Permission type", lateArrival:"Late Arrival", earlyDeparture:"Early Departure", temporaryExit:"Temporary Exit", fromTime:"From time", toTime:"To time", permissionReason:"Permission Reason", hours:"hours", authorizedDuration:"Authorized Duration",
	},
}

export const lang = ref(localStorage.getItem("nagi-language") || "")
export const direction = computed(() => lang.value === "ar" ? "rtl" : "ltr")
export function setLanguage(value) { lang.value = value; localStorage.setItem("nagi-language", value) }
export function t(key) { return messages[lang.value]?.[key] || messages.en[key] || key }

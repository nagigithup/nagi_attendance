<template>
	<div class="app-shell" :dir="direction" :lang="lang" :style="brandStyle">
		<div v-if="loading" class="splash"><div class="mark">ن</div><p>{{ t('loading') }}</p></div>
		<div v-else-if="fatal" class="splash error"><div class="mark">!</div><p>{{ fatal }}</p><button @click="load">{{ t('refresh') }}</button></div>
		<template v-else>
			<header class="topbar">
				<div class="brand">
					<img v-if="data.company.logo" :src="data.company.logo" alt="" />
					<div v-else class="brand-fallback">{{ (data.company.abbr || data.company.name || 'N').slice(0, 2) }}</div>
					<div><strong>{{ data.company.name }}</strong><small>{{ data.company.product_name }}</small></div>
				</div>
				<select v-if="data.companies.length > 1" :value="data.company.name" :aria-label="t('switchCompany')" @change="switchCompany($event.target.value)">
					<option v-for="company in data.companies" :key="company.name">{{ company.name }}</option>
				</select>
			</header>

			<main>
				<section v-if="tab === 'home'" class="view home-view">
					<div class="welcome"><div><small>{{ fullDate }}</small><h1>{{ t('hello') }}، {{ data.employee.first_name || data.employee.employee_name }}</h1></div><Avatar :employee="data.employee" /></div>
					<AttendanceHero v-if="data.today" :today="data.today" :busy="busy" @checkin="checkin" />
					<div v-else class="empty card">{{ t('attendanceDisabled') }}</div>
					<div class="quick-grid" v-if="data.leave">
						<article class="card"><div class="card-title"><h2>{{ t('upcomingLeave') }}</h2><span>↗</span></div><LeaveRows :rows="data.leave.upcoming" :empty="t('noUpcoming')" compact /></article>
						<article class="card"><div class="card-title"><h2>{{ t('leaveBalance') }}</h2><span>◔</span></div><BalanceRows :balances="data.leave.balances" /></article>
					</div>
					<article v-if="data.leave?.pending_approvals?.length" class="card approvals-preview" @click="tab='leave'; leavePane='approvals'">
						<div><small>{{ t('managerApprovals') }}</small><strong>{{ data.leave.pending_approvals.length }}</strong></div><span>←</span>
					</article>
				</section>

				<section v-else-if="tab === 'attendance'" class="view">
					<PageTitle :title="t('attendance')" :subtitle="t('monthlyHistory')" @refresh="loadHistory" />
					<AttendanceHero v-if="data.today" :today="data.today" :busy="busy" @checkin="checkin" />
					<div v-if="historyLoading" class="empty">{{ t('loading') }}</div>
					<template v-else>
						<h2 class="history-heading">{{ t('checkinActivity') }}</h2>
						<div class="records card">
							<div v-for="row in history" :key="row.name" class="record-row checkin-record">
								<div class="date-tile"><strong>{{ dayNumber(row.time) }}</strong><small>{{ monthName(row.time) }}</small></div>
								<div class="grow"><strong>{{ statusLabel(row.log_type) }}</strong><small>{{ row.shift || t('outsideShift') }}</small></div>
								<div class="times"><span>{{ timeLabel(row.time) }}</span></div>
							</div>
							<div v-if="!history.length" class="empty">{{ t('noAttendance') }}</div>
						</div>
						<template v-if="attendanceHistory.length">
							<h2 class="history-heading">{{ t('dailyAttendance') }}</h2>
							<div class="records card">
								<div v-for="row in attendanceHistory" :key="row.name" class="record-row">
									<div class="date-tile"><strong>{{ dayNumber(row.attendance_date) }}</strong><small>{{ monthName(row.attendance_date) }}</small></div>
									<div class="grow"><strong>{{ statusLabel(row.status) }}</strong><small>{{ row.shift || '—' }}</small></div>
									<div class="times"><span>{{ timeLabel(row.in_time) }}</span><span>{{ timeLabel(row.out_time) }}</span></div>
									<span v-if="row.late_entry" class="badge warning">{{ t('late') }}</span>
								</div>
							</div>
						</template>
					</template>
				</section>

				<section v-else-if="tab === 'leave'" class="view">
					<PageTitle :title="t('leave')" :subtitle="t('leaveBalance')" @refresh="load" />
					<div v-if="!data.leave" class="empty card">{{ t('leaveDisabled') }}</div>
					<template v-else>
						<div class="segmented">
							<button :class="{active:leavePane==='request'}" @click="leavePane='request'">{{ t('requestLeave') }}</button>
							<button :class="{active:leavePane==='history'}" @click="leavePane='history'">{{ t('history') }}</button>
							<button v-if="data.leave.pending_approvals.length" :class="{active:leavePane==='approvals'}" @click="leavePane='approvals'">{{ t('managerApprovals') }} ({{ data.leave.pending_approvals.length }})</button>
						</div>
						<form v-if="leavePane==='request'" class="card form-card" @submit.prevent="submitLeave">
							<div v-if="data.leave.configuration_error" class="notice warning">{{ t('settingsMissing') }}<small>{{ data.leave.configuration_error }}</small></div>
							<label>{{ t('leaveType') }}<select v-model="leaveForm.leave_type" required><option value="" disabled>{{ t('select') }}</option><option v-for="type in data.leave.types" :key="type">{{ type }}</option></select></label>
							<div class="form-grid"><label>{{ t('fromDate') }}<input v-model="leaveForm.from_date" type="date" required /></label><label>{{ t('toDate') }}<input v-model="leaveForm.to_date" type="date" :min="leaveForm.from_date" required /></label></div>
							<label class="check"><input v-model="leaveForm.half_day" type="checkbox" /> <span>{{ t('halfDay') }}</span></label>
							<label v-if="leaveForm.half_day">{{ t('halfDay') }}<input v-model="leaveForm.half_day_date" type="date" :min="leaveForm.from_date" :max="leaveForm.to_date" required /></label>
							<label>{{ t('reason') }}<textarea v-model="leaveForm.description" rows="4"></textarea></label>
							<button class="primary" :disabled="busy || !data.leave.types.length">{{ busy ? t('loading') : t('submit') }}</button>
						</form>
						<div v-else-if="leavePane==='history'" class="card"><LeaveRows :rows="data.leave.applications" :empty="t('noPending')" actions @cancel="cancelLeave" /></div>
						<div v-else class="card"><ApprovalRows :rows="data.leave.pending_approvals" :busy="busy" @action="leaveAction" /></div>
					</template>
				</section>

				<section v-else-if="tab === 'permission'" class="view">
					<PageTitle :title="t('permission')" :subtitle="t('shortPermission')" @refresh="load" />
					<div class="segmented">
						<button :class="{active:permissionPane==='request'}" @click="permissionPane='request'">{{ t('requestPermission') }}</button>
						<button :class="{active:permissionPane==='history'}" @click="permissionPane='history'">{{ t('myRequests') }}</button>
						<button v-if="data.short_permission.pending_approvals.length" :class="{active:permissionPane==='approvals'}" @click="permissionPane='approvals'">{{ t('pendingPermissionApprovals') }} ({{ data.short_permission.pending_approvals.length }})</button>
					</div>
					<form v-if="permissionPane==='request'" class="card form-card" @submit.prevent="submitPermission">
						<label>{{ t('permissionDate') }}<input v-model="permissionForm.permission_date" type="date" required /></label>
						<label>{{ t('permissionType') }}<select v-model="permissionForm.permission_type" required><option value="" disabled>{{ t('select') }}</option><option value="Late Arrival">{{ t('lateArrival') }}</option><option value="Early Departure">{{ t('earlyDeparture') }}</option><option value="Temporary Exit">{{ t('temporaryExit') }}</option></select></label>
						<div class="form-grid"><label>{{ t('fromTime') }}<input v-model="permissionForm.from_time" type="time" required /></label><label>{{ t('toTime') }}<input v-model="permissionForm.to_time" type="time" required /></label></div>
						<label>{{ t('permissionReason') }}<textarea v-model="permissionForm.reason" rows="4"></textarea></label>
						<button class="primary" :disabled="busy">{{ busy ? t('loading') : t('submit') }}</button>
					</form>
					<PermissionRows v-else :rows="permissionPane==='history' ? data.short_permission.requests : data.short_permission.pending_approvals" :busy="busy" :approvals="permissionPane==='approvals'" @action="permissionAction" @cancel="cancelPermission" />
				</section>

				<section v-else-if="tab === 'account'" class="view">
					<PageTitle :title="t('account')" :subtitle="t('profile')" />
					<article class="profile-card card"><Avatar :employee="data.employee" large /><h1>{{ data.employee.employee_name }}</h1><p>{{ data.employee.designation || '—' }}</p></article>
					<div class="details card">
						<InfoRow :label="t('employeeId')" :value="data.employee.name" />
						<InfoRow :label="t('department')" :value="data.employee.department || '—'" />
						<InfoRow :label="t('designation')" :value="data.employee.designation || '—'" />
						<InfoRow :label="t('company')" :value="data.employee.company" />
					</div>
					<div class="card settings"><label>{{ t('language') }}<select :value="lang" @change="changeLanguage($event.target.value)"><option value="ar">{{ t('arabic') }}</option><option value="en">{{ t('english') }}</option></select></label><button class="logout text-button" :disabled="busy" @click="logout">{{ t('logout') }}</button></div>
				</section>
			</main>

			<nav class="bottom-nav">
				<button v-for="item in tabs" :key="item.id" :class="{active:tab===item.id}" @click="openTab(item.id)"><span v-html="item.icon"></span><small>{{ t(item.id) }}</small></button>
			</nav>
			<div v-if="toast" class="toast" :class="toast.type">{{ toast.text }}</div>
		</template>
	</div>
</template>

<script setup>
import { computed, defineComponent, h, reactive, ref } from "vue"
import { direction, lang, setLanguage, t } from "./i18n"

const data = ref(null), loading = ref(true), fatal = ref(""), busy = ref(false), toast = ref(null)
const tab = ref("home"), leavePane = ref("request"), permissionPane = ref("request"), history = ref([]), attendanceHistory = ref([]), historyLoading = ref(false), activeCompany = ref("")
const todayISO = new Date().toLocaleDateString("en-CA")
const leaveForm = reactive({leave_type:"",from_date:todayISO,to_date:todayISO,half_day:false,half_day_date:todayISO,description:""})
const permissionForm = reactive({permission_date:todayISO,permission_type:"",from_time:"",to_time:"",reason:""})
const icons = {
	home:'<svg viewBox="0 0 24 24"><path d="m3 11 9-8 9 8v10h-6v-6H9v6H3z"/></svg>',
	attendance:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
	leave:'<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4m8-4v4M3 10h18"/></svg>',
	permission:'<svg viewBox="0 0 24 24"><path d="M12 3v9l4 2M5 5a10 10 0 1 0 14 2"/></svg>',
	account:'<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>'
}
const tabs = computed(()=>Object.keys(icons).filter(id=>id!=="permission"||data.value?.settings?.enable_short_permission).map(id=>({id,icon:icons[id]})))
const brandStyle = computed(()=>({"--brand":data.value?.company?.primary_color || "#176B5B"}))
const locale = computed(()=>lang.value === "ar" ? "ar-SA" : "en-GB")
const fullDate = computed(()=>new Intl.DateTimeFormat(locale.value,{weekday:"long",day:"numeric",month:"long",year:"numeric"}).format(new Date()))

async function api(method, args={}, post=false) {
	const options = {method:post?"POST":"GET",headers:{"Accept":"application/json","X-Frappe-CSRF-Token":window.csrf_token}}
	if (post) { options.headers["Content-Type"]="application/json"; options.body=JSON.stringify(args) }
	const query = !post && Object.keys(args).length ? "?"+new URLSearchParams(args) : ""
	const response = await fetch(`/api/method/nagi_attendance.mobile_api.${method}${query}`,options)
	const payload = await response.json().catch(()=>({}))
	if (!response.ok || payload.exc_type) throw new Error(payload._server_messages ? JSON.parse(payload._server_messages).map(v=>JSON.parse(v).message).join("\n") : payload.message || t("error"))
	return payload.message
}
async function load() {
	loading.value=!data.value; fatal.value=""
	try {
		data.value=await api("bootstrap",activeCompany.value?{company:activeCompany.value}:{})
		activeCompany.value=data.value.company.name
		if (!lang.value) setLanguage(data.value.company.default_language || "ar")
		document.documentElement.lang=lang.value; document.documentElement.dir=direction.value
		document.querySelector('meta[name="theme-color"]').content=data.value.company.primary_color
	} catch(e) { fatal.value=e.message } finally { loading.value=false }
}
async function switchCompany(company) { activeCompany.value=company; history.value=[]; attendanceHistory.value=[]; await load() }
function changeLanguage(value) { setLanguage(value); document.documentElement.lang=value; document.documentElement.dir=direction.value }
function openTab(value) { tab.value=value; if(value==="attendance"&&!history.value.length) loadHistory(); window.scrollTo({top:0,behavior:"smooth"}) }
function notify(text,type="success") { toast.value={text,type}; setTimeout(()=>toast.value=null,3500) }

function getPosition() {
	return new Promise((resolve,reject)=>{
		if(!navigator.geolocation) return reject(new Error(t("locationRequired")))
		navigator.geolocation.getCurrentPosition(resolve,()=>reject(new Error(t("locationRequired"))),{enableHighAccuracy:true,timeout:15000,maximumAge:0})
	})
}
async function checkin(action) {
	if(busy.value) return
	busy.value=true
	try {
		let coords={}
		if(data.value.settings.enable_gps_validation) { const position=await getPosition(); coords={latitude:position.coords.latitude,longitude:position.coords.longitude,accuracy:position.coords.accuracy} }
		await api("create_checkin",{log_type:action,company:activeCompany.value,...coords},true); notify(t("success")); await load()
	} catch(e) { notify(e.message,"error") } finally { busy.value=false }
}
async function loadHistory() {
	if(!data.value?.settings.allow_attendance_history) return
	historyLoading.value=true
	try { const result=await api("get_attendance_history",{company:activeCompany.value}); history.value=result.checkins || []; attendanceHistory.value=result.records || [] }
	catch(e){notify(e.message,"error")} finally{historyLoading.value=false}
}
async function submitLeave() {
	if(busy.value)return; busy.value=true
	try { await api("create_leave_application",{...leaveForm,half_day:leaveForm.half_day?1:0,company:activeCompany.value},true); notify(t("success")); leavePane.value="history"; await load() }
	catch(e){notify(e.message,"error")}finally{busy.value=false}
}
async function leaveAction({name,action}) { if(busy.value||!confirm(t("confirmAction")))return;busy.value=true;try{await api("apply_leave_action",{name,action},true);notify(t("success"));await load()}catch(e){notify(e.message,"error")}finally{busy.value=false} }
async function cancelLeave(name) { if(busy.value||!confirm(t("confirmAction")))return;busy.value=true;try{await api("cancel_leave_application",{name,company:activeCompany.value},true);notify(t("success"));await load()}catch(e){notify(e.message,"error")}finally{busy.value=false} }
async function submitPermission() { if(busy.value)return;busy.value=true;try{await api("create_permission_request",{...permissionForm,company:activeCompany.value},true);notify(t("success"));permissionPane.value="history";await load()}catch(e){notify(e.message,"error")}finally{busy.value=false} }
async function permissionAction({name,action}) { if(busy.value||!confirm(t("confirmAction")))return;busy.value=true;try{await api("apply_permission_action",{name,action},true);notify(t("success"));await load()}catch(e){notify(e.message,"error")}finally{busy.value=false} }
async function cancelPermission(name) { if(busy.value||!confirm(t("confirmAction")))return;busy.value=true;try{await api("cancel_permission_request",{name,company:activeCompany.value},true);notify(t("success"));await load()}catch(e){notify(e.message,"error")}finally{busy.value=false} }
async function logout() {
	if (busy.value) return
	busy.value = true
	try {
		const response = await fetch("/api/method/logout", {
			method: "POST",
			credentials: "same-origin",
			headers: {"Accept":"application/json", "X-Frappe-CSRF-Token":window.csrf_token},
		})
		if (!response.ok) throw new Error(t("error"))
		window.location.replace("/login?redirect-to=/attendance")
	} catch (e) {
		notify(e.message || t("error"), "error")
		busy.value = false
	}
}
function dateLabel(value,options={day:"numeric",month:"short",year:"numeric"}) { return value?new Intl.DateTimeFormat(locale.value,options).format(new Date(`${String(value).slice(0,10)}T12:00:00`)):"—" }
function dayNumber(v){return dateLabel(v,{day:"numeric"})} function monthName(v){return dateLabel(v,{month:"short"})}
function timeLabel(value){if(!value)return"—";const d=new Date(String(value).replace(" ","T"));return Number.isNaN(d.getTime())?String(value).slice(11,16):new Intl.DateTimeFormat(locale.value,{hour:"2-digit",minute:"2-digit"}).format(d)}
function statusLabel(status){const map={IN:"checkIn",OUT:"checkOut",Present:"present",Absent:"absent",Late:"late","On Leave":"onLeave",Open:"open",Approved:"approved",Rejected:"rejected",Cancelled:"cancelled","Checked In":"checkedIn","Not Checked In":"notChecked"};return t(map[status]||status)||status}

const Avatar=defineComponent({props:{employee:Object,large:Boolean},setup(p){return()=>h("div",{class:["avatar",p.large&&"large"]},p.employee.image?h("img",{src:p.employee.image,alt:""}):(p.employee.employee_name||"?").slice(0,1))}})
const PageTitle=defineComponent({props:{title:String,subtitle:String},emits:["refresh"],setup(p,{emit}){return()=>h("div",{class:"page-title"},[h("div",[h("small",p.subtitle),h("h1",p.title)]),h("button",{onClick:()=>emit("refresh"),title:t("refresh")},"↻")])}})
const InfoRow=defineComponent({props:{label:String,value:[String,Number]},setup:p=>()=>h("div",{class:"info-row"},[h("span",p.label),h("strong",p.value)])})
const AttendanceHero=defineComponent({props:{today:Object,busy:Boolean},emits:["checkin"],setup(p,{emit}){return()=>h("article",{class:"attendance-hero"},[h("div",{class:"status-line"},[h("span",{class:"pulse"}),h("strong",statusLabel(p.today.status))]),h("div",{class:"hero-time"},timeLabel(p.today.last_log?.time)),h("p",p.today.shift?`${p.today.shift.name} · ${String(p.today.shift.start_time).slice(0,5)}–${String(p.today.shift.end_time).slice(0,5)}`:t("noShift")),h("button",{class:"check-button",disabled:p.busy,onClick:()=>emit("checkin",p.today.next_action)},p.busy?t("loading"):(p.today.next_action==="IN"?t("checkIn"):t("checkOut")))])}})
const BalanceRows=defineComponent({props:{balances:Object},setup:p=>()=>{const rows=Object.entries(p.balances||{});return h("div",{class:"balance-list"},rows.length?rows.map(([name,v])=>h("div",[h("span",name),h("strong",String(v.balance_leaves??0))])):h("div",{class:"empty small"},t("noBalance")))}})
const LeaveRows=defineComponent({props:{rows:Array,empty:String,compact:Boolean,actions:Boolean},emits:["cancel"],setup(p,{emit}){return()=>h("div",{class:"leave-list"},p.rows?.length?p.rows.map(row=>h("div",{class:"leave-row"},[h("div",{class:"grow"},[h("strong",row.leave_type),h("small",`${dateLabel(row.from_date)} – ${dateLabel(row.to_date)} · ${row.total_leave_days} ${t("days")}`)]),h("span",{class:["badge",String(row.status).toLowerCase()]},statusLabel(row.status)),p.actions&&row.docstatus===1&&row.status!=="Rejected"?h("button",{class:"text-button danger",onClick:()=>emit("cancel",row.name)},t("cancel")):null])):h("div",{class:"empty small"},p.empty))}})
const ApprovalRows=defineComponent({props:{rows:Array,busy:Boolean},emits:["action"],setup(p,{emit}){return()=>h("div",{class:"leave-list"},p.rows?.length?p.rows.map(row=>h("article",{class:"approval-row"},[h("div",[h("strong",row.employee_name),h("span",row.leave_type)]),h("p",`${dateLabel(row.from_date)} – ${dateLabel(row.to_date)} · ${row.total_leave_days} ${t("days")}`),row.description?h("small",row.description):null,h("div",{class:"approval-actions"},(row.actions||[]).map(action=>h("button",{disabled:p.busy,class:action.toLowerCase().includes("reject")?"secondary":"primary",onClick:()=>emit("action",{name:row.name,action})},action.toLowerCase().includes("reject")?t("reject"):t("approve"))))])):h("div",{class:"empty small"},t("noPending")))}})
const PermissionRows=defineComponent({props:{rows:Array,busy:Boolean,approvals:Boolean},emits:["action","cancel"],setup(p,{emit}){return()=>h("div",{class:"card leave-list"},p.rows?.length?p.rows.map(row=>h("article",{class:"approval-row"},[h("div",[h("strong",p.approvals?row.employee_name:t(row.permission_type.replace(" ","").replace(/^./,c=>c.toLowerCase()))),h("span",statusLabel(row.status))]),h("p",`${dateLabel(row.permission_date)} · ${String(row.from_time).slice(0,5)}–${String(row.to_time).slice(0,5)} · ${row.duration_hours} ${t("hours")}`),row.reason?h("small",row.reason):null,p.approvals?h("div",{class:"approval-actions"},[h("button",{disabled:p.busy,class:"primary",onClick:()=>emit("action",{name:row.name,action:"Approve"})},t("approve")),h("button",{disabled:p.busy,class:"secondary",onClick:()=>emit("action",{name:row.name,action:"Reject"})},t("reject"))]):["Pending","Approved"].includes(row.status)?h("button",{class:"text-button danger",onClick:()=>emit("cancel",row.name)},t("cancel")):null])):h("div",{class:"empty small"},t("noPending")))}})

load()
</script>

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, ArrowRight, Check, CircleAlert, RefreshCw, Save } from 'lucide-react'
import { ApiError, request } from './api'
import { Amount, buttonClass, FieldError, inputClass, Items, primaryClass, ScratchFields } from './FormFields'
import Header from './Header'
import ReportView from './ReportView'
import { bodegaFields, errorStep, gasFields, independentFields, initialForm, itemGroups, formFromReport, pendingDates, steps } from './report'
import type { AmountKey, CatalogSlot, FieldErrors, FormState, Report, Session } from './report'

function Login({ onLogin, busy }: { onLogin: (username: string, password: string) => void; busy: boolean }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  return (
    <main className="mx-auto max-w-md px-4 py-10 sm:px-5 sm:py-14">
      <h1 className="text-2xl font-bold sm:text-3xl">Sign in to your store</h1>
      <p className="mt-3 text-sm leading-6 text-slate-600">Your store reports are available to authorized team members.</p>
      <form onSubmit={(event) => { event.preventDefault(); onLogin(username, password) }} className="mt-7 space-y-5 rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
        <label className="block text-sm font-medium">Username<input required autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} className={`${inputClass} mt-2`} /></label>
        <label className="block text-sm font-medium">Password<input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} className={`${inputClass} mt-2`} /></label>
        <button type="submit" disabled={busy} className={`${primaryClass} w-full`}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </main>
  )
}

function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [storeId, setStoreId] = useState<number | null>(null)
  const [catalog, setCatalog] = useState<CatalogSlot[]>([])
  const [reports, setReports] = useState<Report[]>([])
  const [form, setForm] = useState<FormState>(initialForm)
  const [step, setStep] = useState(0)
  const [view, setView] = useState<Report | null>(null)
  const [editing, setEditing] = useState<number | null>(null)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadedHistoryKey, setLoadedHistoryKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [authBusy, setAuthBusy] = useState(false)
  const [reload, setReload] = useState(0)
  const [historyReload, setHistoryReload] = useState(0)
  const formRef = useRef<HTMLFormElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const generation = useRef(0)
  const userId = session?.user?.id
  const historyKey = `${userId ?? ''}:${storeId ?? ''}:${historyReload}`
  const reportsLoading = Boolean(userId && storeId != null && loadedHistoryKey !== historyKey)

  const reset = (date?: string) => {
    setForm({ ...initialForm(), ...(date ? { report_date: date } : {}) })
    setStep(0); setEditing(null); setView(null); setErrors({}); setError(''); setNotice('')
  }

  useEffect(() => {
    let cancelled = false
    const bootstrap = async () => {
      setLoading(true); setError('')
      try {
        const [auth, data] = await Promise.all([request<Session>('/api/auth/session/'), request<{ slots: CatalogSlot[] }>('/api/lottery/catalog/')])
        if (!Array.isArray(auth.stores) || !Array.isArray(data.slots) || data.slots.length !== 20) throw new ApiError('The report service returned incomplete setup information. Please retry.')
        if (!cancelled) { setSession(auth); setStoreId(auth.stores[0]?.id ?? null); setCatalog(data.slots) }
      } catch (failure) {
        if (!cancelled) setError(failure instanceof Error ? failure.message : 'Unable to load the report service.')
      } finally { if (!cancelled) setLoading(false) }
    }
    void bootstrap()
    return () => { cancelled = true }
  }, [reload])

  const expireSession = () => {
    generation.current += 1
    setSession(null); setStoreId(null); setReports([]); reset(); setSaving(false)
    setError('Your session has expired. Sign in again to continue.')
    // Refresh the CSRF token without losing the sign-in message.
    void request<Session>('/api/auth/session/').then(setSession).catch(() => {})
  }

  useEffect(() => {
    if (!userId || storeId == null) return
    let cancelled = false
    const currentGeneration = generation.current
    void request<{ reports: Report[] }>('/api/reports/', { headers: { 'X-Store-ID': String(storeId) } })
      .then((data) => {
        if (!Array.isArray(data.reports)) throw new ApiError('The report service returned an invalid history. Please retry.')
        if (!cancelled && generation.current === currentGeneration) { setReports(data.reports); setLoadedHistoryKey(historyKey) }
      })
      .catch((failure) => {
        if (cancelled || generation.current !== currentGeneration) return
        setLoadedHistoryKey(historyKey)
        if (failure instanceof ApiError && failure.status === 401) expireSession()
        else setError(failure instanceof Error ? failure.message : 'Unable to load report history.')
      })
    return () => { cancelled = true }
  }, [userId, storeId, historyKey])

  useEffect(() => { headingRef.current?.focus() }, [step, editing])

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }))
    setErrors((current) => Object.fromEntries(Object.entries(current).filter(([path]) => path !== key && !path.startsWith(`${key}.`))))
  }

  const login = async (username: string, password: string) => {
    setAuthBusy(true); setError('')
    try {
      const auth = session?.csrfToken ? session : await request<Session>('/api/auth/session/')
      const signedIn = await request<Session>('/api/auth/login/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': auth.csrfToken }, body: JSON.stringify({ username, password }) })
      generation.current += 1
      setSession(signedIn); setStoreId(signedIn.stores[0]?.id ?? null); reset()
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to sign in.') }
    finally { setAuthBusy(false) }
  }

  const logout = async () => {
    if (authBusy) return
    setAuthBusy(true); setError('')
    try {
      const auth = await request<Session>('/api/auth/logout/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': session?.csrfToken ?? '' }, body: '{}' })
      generation.current += 1
      setSession(auth); setStoreId(null); setReports([]); reset(); setSaving(false)
    } catch (failure) { if (failure instanceof ApiError && failure.status === 401) expireSession(); else setError(failure instanceof Error ? failure.message : 'Unable to sign out. Please retry.') }
    finally { setAuthBusy(false) }
  }

  const changeStore = (id: number) => {
    generation.current += 1
    setStoreId(id); setReports([]); reset(); setSaving(false)
  }

  const editReport = (report: Report) => {
    setForm(formFromReport(report)); setEditing(report.id); setView(null); setStep(0); setErrors({}); setError(''); setNotice('')
  }

  const advance = () => {
    const existingDayClose = reports.find((report) => report.report_date === form.report_date && report.close_type === 'day' && report.id !== editing)
    if (step === 0 && form.close_type === 'day' && existingDayClose) {
      setError(`A day close already exists for ${form.report_date}. Edit that report instead.`)
      setErrors({ report_date: 'A day close already exists for this date.' })
      return
    }
    if (formRef.current?.reportValidity()) setStep((current) => Math.min(current + 1, steps.length - 1))
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (step < steps.length - 1) { advance(); return }
    if (saving || !formRef.current?.reportValidity() || !session?.user || storeId == null) return
    const currentGeneration = generation.current
    setSaving(true); setErrors({}); setError(''); setNotice('')
    const submittedScratch = form.scratch_offs.filter((row) => row.recorded !== false).map(({ slot_number, ending_number, new_roll_count }) => ({ slot_number, ending_number, new_roll_count: Number(new_roll_count) }))
    const headers = { 'Content-Type': 'application/json', 'X-CSRFToken': session.csrfToken, 'X-Store-ID': String(storeId) }
    try {
      const saved = await request<Report>(editing ? `/api/reports/${editing}/` : '/api/reports/', {
        method: editing ? 'PATCH' : 'POST', headers,
        body: JSON.stringify({ ...form, scratch_offs: submittedScratch }),
      })
      if (generation.current !== currentGeneration) return
      setView(saved); setEditing(null)
      // Older edits recalculate dependent closes, so replace the whole history.
      try {
        const latest = await request<{ reports: Report[] }>('/api/reports/', { headers: { 'X-Store-ID': String(storeId) } })
        if (!Array.isArray(latest.reports)) throw new ApiError('Invalid report history.')
        if (generation.current === currentGeneration) { setReports(latest.reports); setView(latest.reports.find((report) => report.id === saved.id) ?? saved) }
      } catch (failure) {
        if (generation.current !== currentGeneration) return
        if (failure instanceof ApiError && failure.status === 401) { expireSession(); return }
        setReports([])
        setNotice('Your report was saved. History could not be refreshed; retry to load the latest calculated reports.')
      }
    } catch (failure) {
      if (generation.current !== currentGeneration) return
      if (failure instanceof ApiError && failure.status === 401) { expireSession(); return }
      setError(failure instanceof Error ? failure.message : 'Unable to save this report.')
      if (failure instanceof ApiError) {
        const mappedErrors = Object.fromEntries(Object.entries(failure.errors).map(([path, message]) => {
          const match = /^scratch_offs\.(\d+)(.*)$/.exec(path)
          const submittedRow = match ? submittedScratch[Number(match[1])] : undefined
          const rowIndex = submittedRow ? form.scratch_offs.findIndex((row) => row.slot_number === submittedRow.slot_number) : -1
          return [match && rowIndex >= 0 ? `scratch_offs.${rowIndex}${match[2]}` : path, message]
        }))
        setErrors(mappedErrors)
        const invalidStep = errorStep(mappedErrors)
        if (invalidStep != null) setStep(invalidStep)
      }
    } finally { if (generation.current === currentGeneration) setSaving(false) }
  }

  const amountGroup = (group: readonly (readonly [AmountKey, string])[]) => (
    <div className="grid gap-4 sm:grid-cols-2">{group.map(([key, label]) => <Amount key={key} name={key} label={label} value={form[key]} signed={key === 'bodega_net_difference'} onChange={(value) => update(key, value)} errors={errors} />)}</div>
  )
  const pending = pendingDates(reports)
  const existingDayClose = reports.find((report) => report.report_date === form.report_date && report.close_type === 'day' && report.id !== editing)
  return (
    <div className="min-h-screen bg-[#f5f7f6] text-slate-900">
      <Header reports={reports} onSelect={(report) => { setView(report); setError(''); setErrors({}) }} session={session} storeId={storeId} onStoreChange={changeStore} onLogout={() => { void logout() }} />
      {error && <div role="alert" className="mx-auto mt-5 max-w-6xl px-4 sm:px-8"><div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"><p>{error}</p>
        {Object.keys(errors).length > 0 && <ul className="mt-2 space-y-1">{Object.entries(errors).map(([path, message]) => <li key={path}><button type="button" className="text-left underline underline-offset-2" onClick={() => { const targetStep = errorStep({ [path]: message }); if (targetStep != null) setStep(targetStep); requestAnimationFrame(() => { const input = Array.from(formRef.current?.elements ?? []).find((element) => (element as HTMLInputElement).name === path); (input as HTMLElement | undefined)?.focus() }) }}>{path === 'form' ? message : `${path.replaceAll('_', ' ')}: ${message}`}</button></li>)}</ul>}
        {!Object.keys(errors).length && !authBusy && session?.user && <button type="button" className="mt-2 font-semibold underline" onClick={() => { setError(''); if (!session) setReload((value) => value + 1); else if (session.user) setHistoryReload((value) => value + 1) }}>Retry</button>}
      </div></div>}
      {notice && <div role="status" className="mx-auto mt-5 max-w-6xl px-4 sm:px-8"><p className="rounded-xl bg-amber-50 p-4 text-sm text-amber-900">{notice} <button type="button" className="font-semibold underline" onClick={() => { setNotice(''); setHistoryReload((value) => value + 1) }}>Refresh history</button></p></div>}
      {loading ? <p role="status" className="p-12 text-center text-slate-600">Loading your store…</p>
        : !session ? <main className="mx-auto max-w-md px-4 py-10 sm:px-5 sm:py-12"><h1 className="text-2xl font-bold">Unable to load store setup</h1><p className="mt-3 text-sm text-slate-600">Retry to load the sign-in service and scratch-off catalog.</p><button type="button" onClick={() => setReload((value) => value + 1)} className={`${primaryClass} mt-5 w-full sm:w-auto`}>Retry setup</button></main>
          : !session.user ? <Login onLogin={(username, password) => { void login(username, password) }} busy={authBusy} />
          : storeId == null ? <main className="mx-auto max-w-2xl px-4 py-10 sm:p-8"><h1 className="text-2xl font-bold">No store access yet</h1><p className="mt-3 text-slate-600">Ask your administrator to add your account to a store.</p></main>
            : <>
              {pending.length > 0 && <aside aria-label="Pending day closes" className="mx-auto mt-5 max-w-6xl px-4 sm:px-8"><div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><p className="flex items-center gap-2 font-semibold"><CircleAlert className="shrink-0" size={16} /> Day close still needed</p><p className="mt-1">These dates have shift reports and need a complete day close.</p><div className="mt-3 grid gap-2 sm:flex sm:flex-wrap">{pending.map((date) => <button type="button" key={date} onClick={() => reset(date)} className={`${buttonClass} border-amber-300 bg-white py-2`}>Close {date}</button>)}</div></div></aside>}
              {reportsLoading && <p role="status" className="mx-auto mt-4 max-w-6xl px-4 text-sm text-slate-600 sm:px-8">Loading report history…</p>}
              {view ? <ReportView report={view} onEdit={editReport} onNew={() => reset()} /> : <main className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
                <div className="mb-6 sm:mb-7"><p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-teal-700">Your store, in balance</p><h1 className="text-2xl font-bold sm:text-3xl">{editing ? 'Edit report' : `Close the ${form.close_type}`}</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">Enter machine and register figures. The report calculates differences and remains available by date.</p></div>
                <nav aria-label="Close progress" className="-mx-4 mb-5 flex snap-x gap-1 overflow-x-auto px-4 pb-2 sm:mx-0 sm:mb-6 sm:px-0">{steps.map(({ label }, index) => <button type="button" key={label} disabled={index > step || saving} aria-current={index === step ? 'step' : undefined} onClick={() => setStep(index)} className={`flex min-h-10 shrink-0 snap-start items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold ${index === step ? 'bg-teal-800 text-white' : index < step ? 'bg-teal-100 text-teal-800' : 'bg-white text-slate-500'}`}><span className="flex size-5 items-center justify-center rounded-full bg-black/10">{index < step ? <Check size={12} /> : index + 1}</span>{label}</button>)}</nav>
                <form ref={formRef} onSubmit={(event) => { void submit(event) }} className="rounded-2xl border border-slate-200 bg-white shadow-sm sm:rounded-3xl">
                  <fieldset disabled={saving} className="min-w-0 border-0 p-4 sm:p-8">
                    <legend className="sr-only">{steps[step].label}</legend>
                    <h2 ref={headingRef} tabIndex={-1} className={`${step === 2 ? 'sr-only' : 'mb-5 text-xl font-bold'} outline-none`}>{step === 0 ? 'Choose your close' : steps[step].label}</h2>
                    {step === 0 && <div className="space-y-6">
                      <p className="text-sm text-slate-600">Day close is required; shift closes can be saved during the day.</p>
                      <div className="max-w-xs"><label htmlFor="report_date" className="mb-2 block text-sm font-medium">Business date</label><input id="report_date" name="report_date" required type="date" value={form.report_date} onChange={(event) => update('report_date', event.target.value)} aria-invalid={Boolean(errors.report_date)} aria-describedby={errors.report_date ? 'report_date-error' : undefined} className={inputClass} /><FieldError name="report_date" errors={errors} /></div>
                      <div role="group" aria-label="Close type" className="grid gap-3 sm:grid-cols-2">{(['day', 'shift'] as const).map((type) => { const unavailable = type === 'day' && Boolean(existingDayClose); return <button type="button" key={type} aria-pressed={form.close_type === type} disabled={unavailable} title={unavailable ? 'A day close already exists for this date.' : undefined} onClick={() => update('close_type', type)} className={`rounded-2xl border p-4 text-left disabled:cursor-not-allowed disabled:opacity-50 ${form.close_type === type ? 'border-teal-600 bg-teal-50' : 'border-slate-200'}`}><strong className="block">{type === 'day' ? 'Day close' : 'Shift close'}</strong><span className="mt-1 block text-sm text-slate-600">{unavailable ? 'Already saved for this date.' : type === 'day' ? 'Complete end-of-day reconciliation.' : 'Checkpoint during the business day.'}</span></button> })}</div><FieldError name="close_type" errors={errors} />
                      {existingDayClose && <p role="alert" className="max-w-xl rounded-xl bg-amber-50 p-3 text-sm text-amber-900">A day close already exists for {form.report_date}. <button type="button" className="font-semibold underline" onClick={() => editReport(existingDayClose)}>Open the existing close</button>, or choose a shift close.</p>}
                      <div className="max-w-md"><label htmlFor="close_label" className="mb-2 block text-sm font-medium">Close name <span className="font-normal text-slate-500">(optional)</span></label><input id="close_label" name="close_label" maxLength={80} value={form.close_label} onChange={(event) => update('close_label', event.target.value)} aria-invalid={Boolean(errors.close_label)} aria-describedby={errors.close_label ? 'close_label-error' : undefined} className={inputClass} /><FieldError name="close_label" errors={errors} /></div>
                    </div>}
                    {step === 1 && amountGroup(independentFields)}
                    {step === 2 && <ScratchFields form={form} catalog={catalog} errors={errors} onChange={(value) => update('scratch_offs', value)} />}
                    {step === 3 && amountGroup(bodegaFields)}
                    {step === 4 && <div className="space-y-6">{amountGroup(gasFields)}<p className="text-sm leading-6 text-slate-600">Phone card sales are prepaid phone cards sold at this register. Card payment without including fee is the debit and credit payment total from the separate card machine.</p>{itemGroups.map(({ key, title }) => <Items key={key} name={key} title={title} values={form[key]} onChange={(value) => update(key, value)} errors={errors} />)}</div>}
                  </fieldset>
                  <div className="mobile-action-bar sticky bottom-0 z-10 flex gap-3 rounded-b-2xl border-t border-slate-100 bg-slate-50/95 px-4 py-3 backdrop-blur sm:static sm:justify-between sm:rounded-b-3xl sm:px-8 sm:py-4">
                    <button type="button" disabled={step === 0 || saving} onClick={() => setStep((value) => value - 1)} className={`${buttonClass} flex-1 border-transparent disabled:invisible sm:flex-none`}><ArrowLeft size={16} /> Back</button>
                    {step < steps.length - 1 ? <button type="submit" disabled={catalog.length !== 20} className={`${primaryClass} flex-1 sm:flex-none`}>Continue <ArrowRight size={16} /></button>
                      : <button type="submit" disabled={saving} className={`${primaryClass} flex-1 sm:flex-none`}>{saving ? <RefreshCw className="animate-spin" size={16} /> : <Save size={16} />}{saving ? 'Saving…' : editing ? 'Save changes' : 'Save report'}</button>}
                  </div>
                </form>
              </main>}
            </>}
    </div>
  )
}

export default App

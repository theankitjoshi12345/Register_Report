import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'
import ts from 'typescript'
import { JSDOM } from 'jsdom'

// Compile the actual application for Node's test runner; no second implementation.
const frontend = fileURLToPath(new URL('../', import.meta.url))
const output = path.join(frontend, 'node_modules/.cache/app-tests')
await mkdir(output, { recursive: true })
for (const file of await readdir(path.join(frontend, 'src'))) {
  if (!/\.(tsx|ts)$/.test(file) || file === 'main.tsx') continue
  const source = await readFile(path.join(frontend, 'src', file), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 } }).outputText
    .replace(/from '([.][^']+)'/g, "from '$1.mjs'")
  await writeFile(path.join(output, file.replace(/\.tsx?$/, '.mjs')), compiled)
}
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' })
for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'HTMLSelectElement', 'Event', 'MouseEvent']) globalThis[key] = dom.window[key]
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true })
globalThis.IS_REACT_ACT_ENVIRONMENT = true
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0)
const { createElement, act } = await import('react')
const { createRoot } = await import('react-dom/client')
const { default: App } = await import(pathToFileURL(path.join(output, 'App.mjs')))
const { initialForm, fields, itemGroups, localDate } = await import(pathToFileURL(path.join(output, 'report.mjs')))

const slots = Array.from({ length: 20 }, (_, index) => ({ slot_number: index + 1, ticket_price: '1.00', max_ticket_number: index === 0 ? 24 : 249 }))
const signedIn = { user: { id: 1, username: 'owner' }, stores: [{ id: 1, name: 'Main store' }, { id: 2, name: 'Second store' }], csrfToken: 'signed-in-token' }
const signedOut = { user: null, stores: [], csrfToken: 'anonymous-token' }
const matched = { expected: '0.00', actual: '0.00', difference: '0.00', status: 'match' }
function reportFromForm(form, id = 1) {
  const bodegaAiTicketTotal = form.bodega_ai_tickets.reduce((total, item) => total + Number(item.amount), 0)
  const bodegaAiRegisterBalance = Number(form.bodega_net_difference) + bodegaAiTicketTotal
  return {
    id, report_date: form.report_date, close_type: form.close_type, close_label: form.close_label, created_at: '2026-09-10T12:00:00Z',
    calculated: {
      inputs: Object.fromEntries([...fields.map(([key]) => [key, form[key]]), ...itemGroups.map(({ key }) => [key, form[key]])]),
      scratch_off: {
        sales: '15.00',
        slots: Object.fromEntries(form.scratch_offs.filter((row) => row.recorded !== false).map((row) => [String(row.slot_number), {
          tickets_sold: 5, ticket_price: '1.00', sales: '5.00', new_roll_count: Number(row.new_roll_count),
          starting_number: 3, ending_number: row.ending_number === '' ? null : Number(row.ending_number), ending_exhausted: row.ending_number === '',
        }])),
      }, comparisons: { phone_card_sales: matched, lottery_sales: matched, lottery_payout: matched },
      terminal: {
        cumulative_sales: form.lottery_terminal_sales, cumulative_payout: form.lottery_terminal_payout,
        previous_cumulative_sales: '0.00', previous_cumulative_payout: '0.00',
        shift_sales: form.lottery_terminal_sales, shift_payout: form.lottery_terminal_payout,
      },
      registers: {
        bodega_net_difference: form.bodega_net_difference,
        bodega_ai_ticket_total: bodegaAiTicketTotal.toFixed(2),
        bodega_ai_register_balance: bodegaAiRegisterBalance.toFixed(2),
        gas_net_difference: '20.00',
      },
      normalized_line_items: itemGroups.flatMap(({ key, type: item_type }) => form[key].map((item) => ({ ...item, item_type }))),
      normalized_scratch_offs: form.scratch_offs.map((row) => ({ ...row, ending_number: row.ending_number === '' ? null : Number(row.ending_number), new_roll_count: Number(row.new_roll_count) })),
    },
  }
}
function summaryFromReports(reports) {
  const shifts = reports.filter((report) => report.close_type === 'shift')
  if (!shifts.length) return []
  const latest = shifts.at(-1)
  return [{
    report_date: latest.report_date, shift_count: shifts.length,
    shifts: shifts.map((report) => ({ id: report.id, close_label: report.close_label, created_at: report.created_at, terminal_sales: report.calculated.terminal.shift_sales, terminal_payout: report.calculated.terminal.shift_payout, scratch_off_sales: report.calculated.scratch_off.sales })),
    terminal: { final_cumulative_sales: latest.calculated.terminal.cumulative_sales, final_cumulative_payout: latest.calculated.terminal.cumulative_payout },
    scratch_off: { sales: '15.00', total_new_rolls: 0, new_rolls_by_slot: {}, final_state: {} },
    inputs: Object.fromEntries(fields.map(([key]) => [key, latest.calculated.inputs[key]])),
    line_items: Object.fromEntries(itemGroups.map(({ key }) => [key, { total: '0.00', entries: [] }])),
    registers: { lottery_sales: '0.00', lottery_payout: '0.00', bodega_net_difference: '0.00', bodega_ai_ticket_total: '0.00', bodega_ai_register_balance: '0.00', gas_net_difference: '20.00' },
    comparisons: { phone_card_sales: matched, lottery_sales: matched, lottery_payout: matched },
  }]
}
const completeForm = (overrides = {}) => ({ ...initialForm(), ...Object.fromEntries(fields.map(([key]) => [key, '0.00'])), report_date: '2026-09-10', ...overrides })
let root, container, requests, history, auth, override
beforeEach(() => {
  container = document.createElement('div'); document.body.append(container)
  root = createRoot(container); requests = []; history = []; auth = structuredClone(signedIn); override = null
  globalThis.fetch = async (url, options = {}) => {
    const call = { url, method: options.method ?? 'GET', headers: options.headers ?? {}, body: options.body ? JSON.parse(options.body) : undefined }
    requests.push(call)
    const custom = await override?.(call)
    if (custom) return custom
    if (url === '/api/auth/session/') return json(auth)
    if (url === '/api/auth/login/') { auth = structuredClone(signedIn); return json(auth) }
    if (url === '/api/auth/logout/') { auth = structuredClone(signedOut); return json(auth) }
    if (url === '/api/lottery/catalog/') return json({ slots })
    if (url === '/api/reports/' && call.method === 'GET') return json({ reports: history, daily_summaries: summaryFromReports(history) })
    if (call.method === 'POST' || call.method === 'PATCH') {
      const id = call.method === 'PATCH' ? Number(url.split('/')[3]) : 1
      const saved = reportFromForm(call.body, id)
      history = [saved, ...history.filter((report) => report.id !== id)]
      return json(saved, call.method === 'POST' ? 201 : 200)
    }
    throw new Error(`Unexpected request ${call.method} ${url}`)
  }
})
afterEach(async () => { await act(async () => root.unmount()); container.remove() })
const json = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
async function render() { await act(async () => { root.render(createElement(App)) }); await settle() }
async function settle() { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) }) }
function button(text) {
  const found = [...container.querySelectorAll('button')].find((element) => element.textContent.trim() === text || element.getAttribute('aria-label') === text)
  assert.ok(found, `Missing button: ${text}`)
  return found
}
async function click(text) { await act(async () => button(text).click()); await settle() }
function input(name) {
  const found = container.querySelector(`[name="${name}"]`) ?? container.querySelector(`[aria-label="${name}"]`)
  assert.ok(found, `Missing input: ${name}`)
  return found
}
async function enter(name, value) {
  const element = input(name)
  await act(async () => {
    const prototype = element.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, value)
    element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }))
  })
}
async function fillVisible(amount = '0.00') {
  for (const element of [...container.querySelectorAll('input[type=number][required]')]) await enter(element.name, amount)
}
async function goToGas() {
  await click('Continue'); await fillVisible(); await click('Continue'); await click('Continue'); await fillVisible(); await click('Continue')
}
function currentStep() { return container.querySelector('[aria-current="step"]')?.textContent.trim() }

// Every navigation action uses the real form and native constraint validation.
test('five-step create, full entered figures, edit round-trip, and refreshed dependent history', async () => {
  const later = reportFromForm(completeForm({ report_date: '2026-09-11', close_label: 'Later close' }), 2)
  history = [later]
  await render()
  await enter('report_date', '2026-09-10'); await enter('close_label', 'Evening review')
  await click('Continue')
  assert.match(currentStep(), /Machine totals/)
  await click('Continue'); assert.match(currentStep(), /Machine totals/)
  await fillVisible()
  await enter('phone_card_actual_sales', '-1'); await click('Continue'); assert.match(currentStep(), /Machine totals/)
  await enter('phone_card_actual_sales', '1.001'); await click('Continue'); assert.match(currentStep(), /Machine totals/)
  await enter('phone_card_actual_sales', '17.25'); await click('Continue')
  assert.match(currentStep(), /Scratch-off count/)
  await enter('scratch_offs.0.ending_number', '25'); await click('Continue'); assert.match(currentStep(), /Scratch-off count/)
  await enter('scratch_offs.0.ending_number', '4.5'); assert.equal(input('scratch_offs.0.ending_number').value, '25')
  await enter('scratch_offs.0.ending_number', '4')
  await enter('scratch_offs.1.new_roll_count', '1.5'); await click('Continue'); assert.match(currentStep(), /Scratch-off count/)
  await enter('scratch_offs.1.new_roll_count', '2'); await click('Continue')
  assert.match(currentStep(), /Bodega AI/)
  await fillVisible(); await enter('Bodega net difference sign', '-'); await enter('bodega_net_difference', '3.25'); await click('Continue')
  assert.match(currentStep(), /Verifone/)
  await fillVisible(); await enter('gas_phone_card_sales', '17.25'); await enter('gas_card_payment_sales', '98.50')
  for (const [title, key, amount, description] of [['tickets', 'tickets', '12.50', 'Customer tab'], ['vendor payouts', 'vendor_payouts', '7.00', 'Bread delivery'], ['safe drops', 'safe_drops', '100.00', 'Evening deposit']]) {
    await click(`Add ${title} amount`); await enter(`${key}.0.amount`, amount); await enter(`${key}.0.description`, description)
  }
  await click('Save report')
  assert.match(container.textContent, /Shift report for 2026-09-10/)
  for (const label of ['Verifone total cash sales', 'Verifone lottery sales', 'Verifone lottery payout', 'Verifone phone card sales']) {
    assert.match(container.textContent, new RegExp(label))
  }
  assert.doesNotMatch(container.textContent, /Gas (?:total cash|lottery|phone card)|Gas register/)
  assert.match(container.textContent, /Customer tab/); assert.match(container.textContent, /Bread delivery/); assert.match(container.textContent, /Evening deposit/)
  assert.match(container.textContent, /Starting number/); assert.match(container.textContent, /Value generated/)
  assert.match(container.textContent, /003/); assert.match(container.textContent, /004/); assert.match(container.textContent, /\$5.00/)
  const save = requests.find((call) => call.method === 'POST' && call.url === '/api/reports/')
  assert.equal(save.headers['X-CSRFToken'], 'signed-in-token'); assert.equal(save.headers['X-Store-ID'], '1')
  assert.equal(save.body.bodega_net_difference, '-3.25')
  assert.equal(save.body.gas_phone_card_sales, '17.25'); assert.equal(save.body.gas_card_payment_sales, '98.50'); assert.equal(save.body.gas_card_sales, undefined)
  assert.equal(save.body.tickets[0].amount, '+12.50')
  assert.equal(save.body.scratch_offs[1].ending_number, ''); assert.equal(save.body.scratch_offs[1].new_roll_count, 2)
  await click('Edit'); assert.equal(input('close_label').value, 'Evening review')
  await click('Continue'); assert.equal(input('phone_card_actual_sales').value, '17.25')
  await click('Continue'); assert.equal(input('scratch_offs.0.ending_number').value, '4'); assert.equal(input('scratch_offs.1.new_roll_count').value, '2')
  await click('Continue'); assert.equal(input('Bodega net difference sign').value, '-'); assert.equal(input('bodega_net_difference').value, '3.25')
  await click('Continue'); assert.equal(input('tickets.0.description').value, 'Customer tab'); assert.equal(input('Tickets amount 1 sign').value, '+'); assert.equal(input('tickets.0.amount').value, '12.50'); assert.equal(input('gas_card_payment_sales').value, '98.50')
  override = (call) => { if (call.method === 'PATCH') later.calculated.registers.gas_net_difference = '777.00' }
  await click('Save changes')
  assert.equal(requests.filter((call) => call.url === '/api/reports/' && call.method === 'GET').length, 3)
  await click('2026-09-11Shift Later close'); assert.match(container.textContent, /\$777.00/)
})

test('sign selectors support negative amounts without a minus key', async () => {
  await render(); await goToGas(); await fillVisible()
  await click('Add tickets amount')
  assert.match(container.textContent, /Choose \+ when a ticket is created for the customer and − when the customer pays the ticket/)
  assert.doesNotMatch(container.textContent, /Phone card sales are prepaid phone cards/)
  await enter('Tickets amount 1 sign', '-'); await enter('tickets.0.amount', '8.25')
  await click('Save report')
  const save = requests.find((call) => call.method === 'POST' && call.url === '/api/reports/')
  assert.equal(save.body.tickets[0].amount, '-8.25')
})

test('Bodega AI tickets are optional, positive-only, and adjust Register Balance', async () => {
  await render()
  await click('Continue'); await fillVisible(); await click('Continue'); await click('Continue'); await fillVisible()
  await enter('Bodega net difference sign', '-'); await enter('bodega_net_difference', '50')
  assert.match(container.textContent, /Fill this up if anybody has charged any ticket/)
  await click('Add bodega ai tickets amount')
  assert.equal(container.querySelector('[aria-label="Bodega AI tickets amount 1 sign"]'), null)
  assert.equal(input('bodega_ai_tickets.0.amount').min, '0.01')
  await enter('bodega_ai_tickets.0.amount', '10'); await enter('bodega_ai_tickets.0.description', 'Customer ticket')
  await click('Add bodega ai tickets amount'); await enter('bodega_ai_tickets.1.amount', '10')
  await click('Continue'); await fillVisible(); await click('Save report')
  const save = requests.find((call) => call.method === 'POST' && call.url === '/api/reports/')
  assert.deepEqual(save.body.bodega_ai_tickets, [
    { amount: '10', description: 'Customer ticket' },
    { amount: '10', description: '' },
  ])
  assert.match(container.textContent, /Register Balance/)
  assert.match(container.textContent, /-\$30\.00/)
  await click('Edit'); await click('Continue'); await click('Continue'); await click('Continue')
  assert.equal(input('bodega_ai_tickets.0.amount').value, '10')
  assert.equal(input('bodega_ai_tickets.0.description').value, 'Customer ticket')
})

test('Enter on an earlier step advances without creating a report', async () => {
  await render()
  await act(async () => container.querySelector('form').requestSubmit())
  assert.match(currentStep(), /Machine totals/)
  assert.equal(requests.filter((call) => call.method === 'POST').length, 0)
})

test('nested server field errors return to the relevant step and retain entered data', async () => {
  await render(); await goToGas(); await fillVisible()
  await click('Add tickets amount'); await enter('tickets.0.amount', '2'); await enter('tickets.0.description', 'Keep this')
  override = (call) => call.method === 'POST' ? json({ errors: { scratch_offs: [{ ending_number: ['Ending counter is before the prior reading.'] }], tickets: [{ amount: ['Check this amount.'] }] } }, 400) : null
  await click('Save report')
  assert.match(currentStep(), /Scratch-off count/)
  assert.equal(input('scratch_offs.0.ending_number').getAttribute('aria-invalid'), 'true')
  assert.match(container.textContent, /Ending counter is before the prior reading/)
  await click('Continue'); await click('Continue')
  assert.equal(input('tickets.0.description').value, 'Keep this')
  assert.equal(input('tickets.0.amount').getAttribute('aria-invalid'), 'true')
})

test('non-JSON service failure is actionable and does not lose the form', async () => {
  await render(); await goToGas(); await fillVisible(); await enter('gas_cash_sales', '50')
  override = (call) => call.method === 'POST' ? { ok: false, status: 502, json: async () => { throw new SyntaxError('HTML gateway page') } } : null
  await click('Save report')
  assert.match(container.querySelector('[role=alert]').textContent, /unreadable response/)
  assert.equal(input('gas_cash_sales').value, '50')
  assert.equal(button('Save report').disabled, false)
})

test('login rotates CSRF, store switching scopes requests, and logout clears reports', async () => {
  auth = structuredClone(signedOut)
  await render()
  assert.match(container.textContent, /Sign in to your store/)
  assert.equal(requests.some((call) => call.url === '/api/reports/'), false)
  const loginInputs = container.querySelectorAll('input')
  for (const [index, value] of ['owner', 'correct password'].entries()) {
    await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(loginInputs[index], value); loginInputs[index].dispatchEvent(new Event('input', { bubbles: true })) })
  }
  await click('Sign in')
  assert.equal(requests.find((call) => call.url === '/api/auth/login/').headers['X-CSRFToken'], 'anonymous-token')
  await enter('close_label', 'Old store draft'); await enter('Store', '2'); await settle()
  assert.equal(input('close_label').value, '')
  assert.equal(requests.filter((call) => call.url === '/api/reports/').at(-1).headers['X-Store-ID'], '2')
  await goToGas(); await fillVisible(); await click('Save report')
  const save = requests.find((call) => call.method === 'POST' && call.url === '/api/reports/')
  assert.equal(save.headers['X-CSRFToken'], 'signed-in-token'); assert.equal(save.headers['X-Store-ID'], '2')
  await click('Sign out owner')
  assert.match(container.textContent, /Sign in to your store/); assert.doesNotMatch(container.textContent, /Report for/)
})

test('late history responses cannot populate a different store', async () => {
  let resolveFirst
  const old = reportFromForm(completeForm({ close_label: 'Other store secret' }))
  override = (call) => call.url === '/api/reports/' && call.headers['X-Store-ID'] === '1' ? new Promise((resolve) => { resolveFirst = resolve }) : null
  await render(); await enter('Store', '2'); await settle()
  await act(async () => resolveFirst(json({ reports: [old] }))); await settle()
  assert.doesNotMatch(container.textContent, /Other store secret/)
})

test('401 while saving clears private report state and returns to sign-in', async () => {
  await render(); await goToGas(); await fillVisible()
  override = (call) => { if (call.method === 'POST') { auth = structuredClone(signedOut); return json({ error: 'Sign in required.' }, 401) } return null }
  await click('Save report')
  assert.match(container.textContent, /session has expired/); assert.match(container.textContent, /Sign in to your store/)
  assert.doesNotMatch(container.textContent, /Save report/)
})

test('revoked store access clears private report data and reloads available stores', async () => {
  await render(); await enter('close_label', 'Revoked store private close'); await goToGas(); await fillVisible()
  let saved = false
  override = (call) => {
    if (call.url === '/api/reports/' && call.method === 'POST') {
      saved = true
      auth = { ...signedIn, stores: [signedIn.stores[1]] }
    }
    if (saved && call.url === '/api/reports/' && call.method === 'GET') {
      return call.headers['X-Store-ID'] === '1'
        ? json({ errors: 'Store not found.', code: 'store_access_denied' }, 404)
        : json({ reports: [] })
    }
    return null
  }
  await click('Save report')
  assert.match(container.textContent, /Your access to this store has changed/)
  assert.doesNotMatch(container.textContent, /Revoked store private close|Main store|Report for/)
  assert.match(container.textContent, /Second store/)
  assert.equal(input('close_label').value, '')
  assert.equal(requests.filter((call) => call.url === '/api/reports/' && call.method === 'GET').at(-1).headers['X-Store-ID'], '2')
})

test('saving after the last store membership is revoked clears the draft and history', async () => {
  history = [reportFromForm(completeForm({ close_label: 'Private history' }))]
  await render(); await enter('report_date', '2026-09-11'); await enter('close_label', 'Private draft'); await goToGas(); await fillVisible()
  override = (call) => {
    if (call.url === '/api/reports/' && call.method === 'POST') {
      auth = { ...signedIn, stores: [] }
      return json({ errors: 'Store not found.', code: 'store_access_denied' }, 404)
    }
    return null
  }
  await click('Save report')
  assert.match(container.textContent, /No store access yet/)
  assert.doesNotMatch(container.textContent, /Private history|Private draft|Save report/)
  assert.equal(container.querySelector('summary').textContent.trim(), 'History 0')
})

test('an older session refresh cannot overwrite a later account login', async () => {
  await render(); await goToGas(); await fillVisible()
  let resolveOldSession
  const nextAccount = { user: { id: 2, username: 'next-owner' }, stores: [signedIn.stores[1]], csrfToken: 'next-token' }
  override = (call) => {
    if (call.url === '/api/reports/' && call.method === 'POST') return json({ errors: 'Sign in to access reports.' }, 401)
    if (call.url === '/api/auth/session/' && !resolveOldSession) return new Promise((resolve) => { resolveOldSession = resolve })
    if (call.url === '/api/auth/session/') return json(signedOut)
    if (call.url === '/api/auth/login/') return json(nextAccount)
    return null
  }
  await click('Save report')
  assert.ok(resolveOldSession)
  await click('Retry setup')
  const loginInputs = container.querySelectorAll('input')
  for (const [index, value] of ['next-owner', 'correct password'].entries()) await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(loginInputs[index], value)
    loginInputs[index].dispatchEvent(new Event('input', { bubbles: true }))
  })
  await click('Sign in')
  await act(async () => resolveOldSession(json(signedIn))); await settle()
  assert.ok(button('Sign out next-owner'))
  assert.match(container.textContent, /Second store/)
  assert.doesNotMatch(container.textContent, /Main store/)
})

test('a CSRF rejection preserves the unsaved report', async () => {
  await render(); await goToGas(); await fillVisible(); await enter('gas_cash_sales', '50')
  override = (call) => call.method === 'POST'
    ? json({ errors: 'Your session token has expired. Reload the page and try again.' }, 403)
    : null
  await click('Save report')
  assert.match(container.querySelector('[role=alert]').textContent, /session token has expired/)
  assert.equal(input('gas_cash_sales').value, '50')
  assert.equal(requests.filter((call) => call.url === '/api/auth/session/').length, 1)
})

test('ordinary missing reports do not revoke store access or discard the draft', async () => {
  const saved = reportFromForm(completeForm({ close_label: 'Unsaved private draft' }))
  history = [saved]
  await render(); await click('2026-09-10Shift Unsaved private draft'); await click('Edit'); await goToGas()
  override = (call) => call.method === 'PATCH' ? json({ errors: 'Report not found.' }, 404) : null
  await click('Save changes')
  assert.match(container.querySelector('[role=alert]').textContent, /Report not found/)
  assert.ok(button('Save changes'))
  assert.equal(requests.filter((call) => call.url === '/api/auth/session/').length, 1)
})

test('daily summaries are automatic and shift history still shows legacy missing payments', async () => {
  const legacy = reportFromForm(completeForm({ close_type: 'shift', close_label: 'Morning', gas_phone_card_sales: '12.00', gas_card_payment_sales: null }))
  legacy.calculated.registers.gas_net_difference = null
  history = [legacy]
  await render()
  await click('2026-09-10Daily summary · 1 shift')
  assert.match(container.textContent, /Automatic day end/)
  assert.match(container.textContent, /Calculated from 1 shift/)
  await click('MorningTerminal sales $0.00 · Scratch-offs $15.00')
  assert.match(container.textContent, /older report needs its card payment amount/)
  assert.match(container.textContent, /Needs entry/)
  await click('Edit'); await goToGas()
  assert.equal(input('gas_phone_card_sales').value, '12.00'); assert.equal(input('gas_card_payment_sales').value, '')
  await click('Save changes'); assert.match(currentStep(), /Verifone/)
})

test('business date uses local calendar components rather than a UTC date', () => {
  assert.equal(localDate({ getFullYear: () => 2026, getMonth: () => 8, getDate: () => 10, toISOString: () => '2026-09-11T02:00:00Z' }), '2026-09-10')
})

test('sparse saved scratch readings remain omitted on edit and errors map to the visible slot', async () => {
  const saved = reportFromForm(completeForm())
  saved.calculated.normalized_scratch_offs = [{ slot_number: 3, ending_number: 10, new_roll_count: 0 }]
  history = [saved]
  await render(); await click('2026-09-10Shift'); await click('Edit'); await goToGas(); await fillVisible()
  override = (call) => call.method === 'PATCH' ? json({ errors: { 'scratch_offs.0.ending_number': ['Check slot 3 reading.'] } }, 400) : null
  await click('Save changes')
  const patch = requests.find((call) => call.method === 'PATCH')
  assert.deepEqual(patch.body.scratch_offs, [{ slot_number: 3, ending_number: '10', new_roll_count: 0 }])
  assert.equal(input('scratch_offs.2.ending_number').getAttribute('aria-invalid'), 'true')
  assert.equal(input('scratch_offs.0.ending_number').getAttribute('aria-invalid'), 'false')
  assert.match(container.textContent, /Not recorded. Leave unchanged/)
  await enter('scratch_offs.0.ending_number', '5'); await click('Continue'); await click('Continue')
  override = null; await click('Save changes')
  const lastPatch = requests.filter((call) => call.method === 'PATCH').at(-1)
  assert.deepEqual(lastPatch.body.scratch_offs.map((row) => row.slot_number), [1, 3])
})

test('login failures expose the server message and setup failures offer a working retry', async () => {
  auth = structuredClone(signedOut)
  let catalogFailed = true
  override = (call) => call.url === '/api/lottery/catalog/' && catalogFailed ? json({ errors: 'Catalog is temporarily unavailable.' }, 503) : null
  await render()
  assert.match(container.textContent, /Unable to load store setup/)
  assert.doesNotMatch(container.textContent, /Sign in to your store/)
  catalogFailed = false; await click('Retry setup')
  const loginInputs = container.querySelectorAll('input')
  for (const [index, value] of ['owner', 'wrong password'].entries()) await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(loginInputs[index], value)
    loginInputs[index].dispatchEvent(new Event('input', { bubbles: true }))
  })
  override = (call) => call.url === '/api/auth/login/' ? json({ errors: 'Invalid username or password.' }, 401) : null
  await click('Sign in')
  assert.match(container.querySelector('[role=alert]').textContent, /Invalid username or password/)
})

test('saved reports remain visible when history refresh fails and refresh can recover', async () => {
  await render(); await goToGas(); await fillVisible()
  let saved = false
  override = (call) => {
    if (call.method === 'POST') saved = true
    if (saved && call.url === '/api/reports/' && call.method === 'GET') return json({ errors: 'History unavailable.' }, 503)
    return null
  }
  await click('Save report')
  assert.match(container.textContent, /Your report was saved/); assert.match(container.textContent, /Shift report for/)
  override = null; await click('Refresh history')
  assert.doesNotMatch(container.textContent, /History could not be refreshed/)
  assert.equal(container.querySelector('summary').textContent.trim(), 'History 1')
})

test('a save completing after a store switch cannot show another store report', async () => {
  await render(); await goToGas(); await fillVisible()
  let resolveSave, capturedForm
  override = (call) => call.method === 'POST' ? new Promise((resolve) => { resolveSave = resolve; capturedForm = call.body }) : null
  await click('Save report')
  assert.ok(resolveSave)
  await enter('Store', '2'); await settle()
  await act(async () => resolveSave(json(reportFromForm({ ...capturedForm, close_label: 'Private old store report' }))))
  await settle()
  assert.doesNotMatch(container.textContent, /Private old store report/)
  assert.match(currentStep(), /Shift details/)
})

test('new reporting workflow is shift-only and explains cumulative terminal entry', async () => {
  await render()
  assert.match(container.textContent, /Close a shift/)
  assert.doesNotMatch(container.textContent, /Day closeAlready/)
  await click('Continue')
  assert.match(container.textContent, /Do not subtract earlier shifts/)
  assert.ok(input('lottery_terminal_sales'))
})

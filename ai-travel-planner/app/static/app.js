const $ = (id) => document.getElementById(id);
const money = (n) => `$${Number(n).toLocaleString('en-US')}`;
const dateLabel = (s) => new Date(`${s}T12:00:00`).toLocaleDateString('en-US', {weekday:'long', month:'long', day:'numeric'});
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = (s) => { try { const u = new URL(s); return ['https:', 'http:'].includes(u.protocol) ? esc(u.href) : '#'; } catch { return '#'; } };
let currentPlan = null;

const today = new Date();
const localDate = (offset) => { const d = new Date(today); d.setDate(d.getDate() + offset); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
$('start_date').min = localDate(0);
$('start_date').value = localDate(21);
$('end_date').value = localDate(23);
$('destination').value = 'Istanbul';
$('start_date').addEventListener('change', () => { $('end_date').min = $('start_date').value; if ($('end_date').value < $('start_date').value) $('end_date').value = $('start_date').value; });

fetch('/api/destinations').then(r => r.json()).then(data => { $('destinations').innerHTML = data.map(d => `<option value="${esc(d.key)}">${esc(d.name)}</option>`).join(''); }).catch(() => {});

function render(plan) {
  currentPlan = plan;
  const b = plan.budget;
  const amountClass = b.feasible ? '' : ' over';
  const days = plan.days.map((day, i) => `<article class="day-card"><div class="day-head"><div><div class="day-num">Day ${String(i+1).padStart(2,'0')} · ${esc(dateLabel(day.date))}</div><h3>${esc(day.theme)}</h3></div>${day.weather ? `<span class="weather-pill">${day.weather.temperature_max_c == null ? '' : `${Math.round(day.weather.temperature_max_c)}°C`} ${day.weather.precipitation_probability == null ? '' : `· ${day.weather.precipitation_probability}% rain`}</span>` : ''}</div><div class="timeline">${day.items.map(item => `<div class="timeline-row"><span class="timeline-time">${esc(item.time)}</span><span class="timeline-dot"></span><div class="timeline-info"><strong>${esc(item.title)}</strong><p>${esc(item.detail)}</p>${item.map_url ? `<a href="${safeUrl(item.map_url)}" target="_blank" rel="noopener noreferrer">View map ↗</a>` : ''}</div><span class="timeline-cost">${money(item.estimated_cost_usd)}</span></div>`).join('')}</div><div class="day-total"><span>Day estimate · group</span><span>${money(day.estimated_cost_usd)}</span></div></article>`).join('');
  const booking = [plan.flight && `<a class="booking-link" href="${safeUrl(plan.flight.search_url)}" target="_blank" rel="noopener noreferrer">✈ ${esc(plan.flight.title)} ↗<small>${esc(plan.flight.status === 'live_offer' ? 'Provider offer · recheck availability' : 'Planning allowance · compare actual fares')}</small></a>`, `<a class="booking-link" href="${safeUrl(plan.hotel.search_url)}" target="_blank" rel="noopener noreferrer">⌂ ${esc(plan.hotel.title)} ↗<small>${esc(plan.hotel.status === 'live_offer' ? 'Provider offer · recheck availability' : 'Nightly allowance · compare actual rooms')}</small></a>`].filter(Boolean).join('');
  $('results').innerHTML = `<div class="results-head"><div><span class="section-label">YOUR JOURNEY / ${esc(plan.destination_label.toUpperCase())}</span><h2>${esc(plan.headline)}</h2><p class="results-sub">${esc(plan.summary)}</p></div><div class="result-actions"><button class="ghost-button" id="share-button" type="button">Copy link ↗</button><button class="ghost-button" id="download-button" type="button">Download JSON ↓</button><button class="ghost-button" onclick="window.print()" type="button">Print ↗</button></div></div><div class="status-banner${amountClass}">${b.feasible ? `${money(b.remaining_usd)} of your budget remains` : `${money(-b.remaining_usd)} above your budget · compare stays and flights`}</div><div class="result-grid"><div>${days}</div><aside class="sidebar"><div class="budget-card"><h3>The full picture</h3><p class="big-total">${money(b.estimated_total_usd)}</p><p class="total-caption">estimated for ${plan.request.travelers} traveler${plan.request.travelers === 1 ? '' : 's'} · total budget ${money(b.budget_usd)}</p><div class="progress-track"><div class="progress-fill${amountClass}" style="width:${Math.min(100,Math.round(b.estimated_total_usd/b.budget_usd*100))}%"></div></div>${b.lines.map(l => `<div class="budget-line"><div>${esc(l.label)}<small>${esc(l.basis)} · ${esc(l.status.replace('_',' '))}</small></div><b>${money(l.amount_usd)}</b></div>`).join('')}<div class="budget-foot"><span>Remaining</span><span>${money(b.remaining_usd)}</span></div></div><div class="source-card"><h3>Compare options</h3>${booking}<h3 style="margin-top:25px">Good to know</h3><ul class="caveat-list">${plan.caveats.map(c => `<li>${esc(c)}</li>`).join('')}</ul><h3 style="margin-top:25px">Agent trail</h3><div class="trace">${plan.trace.map(t => `<div><b>${esc(t.agent)}</b> · ${esc(t.outcome)} · ${esc(t.source_kind)} · ${t.duration_ms}ms</div>`).join('')}</div></div></aside></div>`;
  $('results').hidden = false;
  $('share-button').addEventListener('click', async () => { try { await navigator.clipboard.writeText(`${location.origin}/?plan=${plan.id}`); $('share-button').textContent = 'Link copied ✓'; } catch { $('share-button').textContent = 'Copy unavailable'; } });
  $('download-button').addEventListener('click', () => { const blob = new Blob([JSON.stringify(plan,null,2)],{type:'application/json'}); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `wayfinder-${plan.request.destination.toLowerCase().replace(/[^a-z0-9]+/g,'-')}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); });
  $('results').scrollIntoView({behavior:'smooth',block:'start'});
}

function detail(message) { if (Array.isArray(message)) return message.map(x => x.msg).join('; '); return String(message || 'Please try again.'); }
$('planner-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('form-error').hidden = true;
  const start = $('start_date').value, end = $('end_date').value;
  const days = Math.round((new Date(`${end}T00:00:00Z`) - new Date(`${start}T00:00:00Z`))/86400000) + 1;
  if (days < 1 || days > 7) { $('form-error').textContent = 'Choose a trip from 1 to 7 days.'; $('form-error').hidden = false; return; }
  const interests = $('interests').value.split(',').map(x => x.trim()).filter(Boolean);
  if (interests.length < 1 || interests.length > 8) { $('form-error').textContent = 'Enter 1 to 8 interests separated by commas.'; $('form-error').hidden = false; return; }
  const payload = {destination:$('destination').value.trim(), start_date:start, end_date:end, budget_usd:Number($('budget_usd').value), travelers:Number($('travelers').value), interests, origin_iata:$('origin_iata').value.trim().toUpperCase() || null, pace:$('pace').value};
  const button = $('planner-form').querySelector('button[type=submit]'); button.disabled = true; button.innerHTML = 'Coordinating your agents… <span>✧</span>';
  try {
    const response = await fetch('/api/plans', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const result = await response.json();
    if (!response.ok) throw new Error(detail(result.detail));
    history.replaceState(null,'',`/?plan=${result.id}`); render(result);
  } catch(err) { $('form-error').textContent = err.message || 'Could not create the itinerary.'; $('form-error').hidden = false; }
  finally { button.disabled = false; button.innerHTML = 'Create my trip <span>↗</span>'; }
});

const sharedId = new URLSearchParams(location.search).get('plan');
if (sharedId && /^[0-9a-f-]{36}$/i.test(sharedId)) fetch(`/api/plans/${sharedId}`).then(r => { if (!r.ok) throw new Error(); return r.json(); }).then(render).catch(() => {});

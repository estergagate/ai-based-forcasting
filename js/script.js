// FRONTEND DEMO: no database, authentication, or real forecasting.
// ---------------- Sample Data ----------------
let salesRecords = [
  {date:'2026-08-25', product:'Chicken Meal', qty:20, price:85},
  {date:'2026-08-25', product:'Rice Meal', qty:15, price:60},
  {date:'2026-08-26', product:'Pancit', qty:12, price:70},
  {date:'2026-08-27', product:'Bread', qty:30, price:15},
  {date:'2026-08-28', product:'Chicken Meal', qty:18, price:85},
  {date:'2026-08-29', product:'Lugaw', qty:10, price:35},
];

const previousSalesSeries = [1400,1600,1550,1750,1690,1900,1810]; // last 7 days
const forecastSeries       = [1820,1870,1900,1950,2000,2050,2100]; // next 7 days

// ---------------- Navigation ----------------
function showPage(pageId){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.getElementById('page-'+pageId).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  const navBtn = document.querySelector('.nav-item[data-page="'+pageId+'"]');
  if(navBtn) navBtn.classList.add('active');
  const titles = {
    dashboard:'Dashboard', sales:'Sales', forecast:'Sales Forecast',
    processing:'Processing', results:'Forecast Results',
    recommendations:'Recommendations', reports:'Reports', settings:'Settings'
  };
  document.getElementById('page-title').textContent = titles[pageId] || '';
  window.scrollTo(0,0);
}

document.querySelectorAll('[data-page]').forEach(el=>{
  el.addEventListener('click', ()=> showPage(el.getAttribute('data-page')));
});

// ---------------- Login ----------------
document.getElementById('login-form').addEventListener('submit', function(e){
  e.preventDefault();
  enterApp();
});
document.getElementById('demo-login').addEventListener('click', enterApp);

function enterApp(){
  document.getElementById('login-screen').style.display='none';
  document.getElementById('app-screen').style.display='block';
  showPage('dashboard');
}

document.getElementById('logout-btn').addEventListener('click', ()=>{
  document.getElementById('app-screen').style.display='none';
  document.getElementById('login-screen').style.display='flex';
});

// ---------------- Sales table & validation ----------------
function renderSalesTable(){
  const body = document.getElementById('sales-table-body');
  body.innerHTML='';
  salesRecords.forEach(r=>{
    const total = (r.qty * r.price).toFixed(2);
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${formatDate(r.date)}</td><td>${r.product}</td><td>${r.qty}</td><td>₱${Number(r.price).toFixed(2)}</td><td>₱${Number(total).toLocaleString()}</td>`;
    body.appendChild(tr);
  });
}
function formatDate(d){
  if(!d) return '—';
  const dt = new Date(d+'T00:00:00');
  if(isNaN(dt)) return d;
  return dt.toLocaleDateString('en-PH',{month:'short',day:'numeric',year:'numeric'});
}
renderSalesTable();

document.getElementById('add-record-btn').addEventListener('click', ()=>{
  const date = document.getElementById('in-date').value;
  const product = document.getElementById('in-product').value;
  const qty = document.getElementById('in-qty').value;
  const price = document.getElementById('in-price').value;

  const errors = [];
  if(!date) errors.push('Please check the date.');
  if(!product) errors.push('Please select a product.');
  if(!qty || Number(qty) <= 0) errors.push('Please enter a valid quantity.');
  if(!price || Number(price) <= 0) errors.push('Please enter a valid price.');

  const statusEl = document.getElementById('sales-status');
  if(errors.length){
    statusEl.innerHTML = `<div class="status-box status-error">⚠ Some information needs to be corrected.
      <ul class="error-list">${errors.map(e=>'<li>'+e+'</li>').join('')}</ul></div>`;
    return;
  }

  salesRecords.unshift({date, product, qty:Number(qty), price:Number(price)});
  renderSalesTable();
  statusEl.innerHTML = `<div class="status-box status-ok">✓ Sales data is valid — record added successfully.</div>`;
  document.getElementById('in-date').value='';
  document.getElementById('in-product').value='';
  document.getElementById('in-qty').value='';
  document.getElementById('in-price').value='';
});

document.getElementById('import-btn').addEventListener('click', ()=>{
  showToast('Import Sales File is a prototype placeholder — file import will be added in a future version.');
});

// ---------------- Processing → Forecast flow ----------------
function runProcessing(nextPage){
  showPage('processing');
  const fill = document.getElementById('progress-fill');
  const pct = document.getElementById('progress-pct');
  fill.style.width='0%'; pct.textContent='0%';
  let p = 0;
  const timer = setInterval(()=>{
    p += 20;
    if(p>100) p=100;
    fill.style.width=p+'%';
    pct.textContent=p+'%';
    if(p>=100){
      clearInterval(timer);
      setTimeout(()=> showPage(nextPage), 350);
    }
  }, 220);
}

// Quick action / dashboard "View Forecast" already routes via data-page to forecast directly.
// Route the "View Forecast" quick-action through processing for the flow demo:
document.querySelectorAll('.qa-btn[data-page="forecast"]').forEach(btn=>{
  btn.addEventListener('click', (e)=>{ e.stopPropagation(); runProcessing('forecast'); });
});

// ---------------- Forecast chart ----------------
function drawChart(days){
  const svg = document.getElementById('forecast-chart');
  const W=600,H=220,pad=30;
  const prev = days===7 ? previousSalesSeries : extendSeries(previousSalesSeries, 30);
  const fore = days===7 ? forecastSeries : extendSeries(forecastSeries, 30);
  const all = prev.concat(fore);
  const max = Math.max(...all)*1.1;
  const min = Math.min(...all)*0.9;
  const n = prev.length;
  const stepX = (W-2*pad)/(n-1);

  function toPoints(series){
    return series.map((v,i)=>{
      const x = pad + i*stepX;
      const y = H-pad - ((v-min)/(max-min))*(H-2*pad);
      return x+','+y;
    }).join(' ');
  }

  svg.innerHTML = `
    <line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" stroke="#E8DFCF" stroke-width="1"/>
    <polyline points="${toPoints(prev)}" fill="none" stroke="#A97C50" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    <polyline points="${toPoints(fore)}" fill="none" stroke="#4C7A5E" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="0"/>
  `;
}
function extendSeries(base, targetLen){
  const out=[...base];
  let last = base[base.length-1];
  while(out.length < targetLen){
    last = last + (Math.random()*60-10);
    out.push(Math.round(last));
  }
  return out;
}
drawChart(7);

document.querySelectorAll('.period-btn').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('.period-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    drawChart(Number(btn.getAttribute('data-period')));
  });
});

document.getElementById('toggle-model-details').addEventListener('click', function(){
  const el = document.getElementById('model-details');
  el.classList.toggle('open');
  this.textContent = el.classList.contains('open') ? 'Hide Model Details' : 'View Model Details';
});

document.getElementById('generate-forecast-btn').addEventListener('click', ()=>{
  showPage('results');
});

// ---------------- Reports ----------------
document.querySelectorAll('.report-actions button').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    const action = btn.getAttribute('data-action');
    const report = btn.getAttribute('data-report');
    if(action==='print'){
      window.print();
    } else if(action==='view'){
      showToast('Viewing "'+report+'" — sample data shown in prototype.');
    } else if(action==='export'){
      showToast('"'+report+'" export is a prototype placeholder.');
    }
  });
});

// ---------------- Toast ----------------
let toastTimer;
function showToast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=> t.classList.remove('show'), 3200);
}

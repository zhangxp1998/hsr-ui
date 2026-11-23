'use strict';
const $ = (id) => document.getElementById(id);
const statusNames = {disconnected:'未连接',connecting:'连接中',connected:'实时连接',locking:'正在锁屏',locked:'已锁屏',error:'连接异常'};
let token = '', data = null, rendered = null, pending = null, pointerHeld = false, clicking = false;
let lastActivitySent = 0, serverReceived = 0, pollBusy = false;
const boxes = new Map(), rows = new Map();

async function post(route, body={}) {
  const response = await fetch('/api/' + route, {method:'POST',headers:{'Content-Type':'application/json','X-HSR-Token':token},body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '请求失败');
  return result;
}
function note(message) { $('notice').textContent = message; }
function flatten(node, list=[]) { if (!node) return list; list.push(node); (node.children || []).forEach(n => flatten(n, list)); return list; }
function actionable(n) { return Boolean(n.ref && (n.actions?.includes('click') || n.actions?.includes('scroll')) && n.enabled !== false && n.selected !== true); }
function label(n) { let text = n.name || n.key; if (n.value != null && !text.includes(String(n.value))) text += ' · ' + String(n.value); return text; }
function highlight(key, on) { boxes.get(key)?.classList.toggle('emphasized', on); }

async function tap(key) {
  if (clicking || data?.mode !== 'connected' || !rendered) return;
  const node = flatten(rendered.tree).find(n => n.key === key);
  if (!node || !actionable(node)) return;
  const sent = {observationId:rendered.observationId, ref:node.ref};
  clicking = true;
  note('校验并点击：' + node.name + '…');
  try { const result = await post('click', sent); note('已点击：' + result.name); }
  catch (error) { note(error.message + '；请等待新观测，不会自动重试。'); }
  finally { clicking = false; pointerHeld = false; pending = null; await poll(); }
}
function render(snapshot) {
  if (!snapshot) {
    rendered = null; boxes.clear(); rows.clear(); $('nodes').replaceChildren(); $('tree').replaceChildren();
    $('empty').querySelector('h3').textContent = data?.mode === 'locked' ? '已锁屏，实时采集已停止' : '让界面，变成可操作的结构';
    $('empty').querySelector('p').textContent = '点击连接，实时显示识别到的文字与控件位置。点击蓝色框，会同步操作平板。';
    $('empty').hidden = false; $('page-name').textContent = data?.mode === 'locked' ? '平板已锁屏' : '等待连接';
    $('node-count').textContent = '0 节点'; $('state-summary').textContent = '尚无实时数据'; $('state-json').textContent = '{}';
    return;
  }
  if (snapshot.observationId === rendered?.observationId) return;
  rendered = snapshot;
  $('empty').hidden = true;
  $('tree').querySelector('.placeholder')?.remove();
  const [width, height] = snapshot.dimensions;
  $('stage').style.aspectRatio = width + ' / ' + height;
  $('page-name').textContent = snapshot.label || snapshot.page;
  $('dimensions').textContent = width + ' × ' + height;
  const timing = snapshot.timing_ms?.service_total ?? snapshot.timing_ms?.total;
  $('latency').textContent = timing != null ? Math.round(timing) + ' ms' : '— ms';
  const nodes = flatten(snapshot.tree).filter(n => Array.isArray(n.bounds) && n.bounds.length === 4 && n.role !== 'group' && n.role !== 'application');
  const keys = new Set(nodes.map(n => n.key));
  for (const [key, el] of boxes) { if (!keys.has(key)) { el.remove(); boxes.delete(key); rows.get(key)?.remove(); rows.delete(key); } }
  nodes.forEach(n => {
    const canTap = actionable(n), tag = canTap ? 'BUTTON' : 'DIV';
    let box = boxes.get(n.key), row = rows.get(n.key);
    if (!box || box.tagName !== tag) {
      box?.remove(); row?.remove(); box = document.createElement(tag); row = document.createElement(tag);
      box.appendChild(document.createElement('span'));
      row.appendChild(document.createElement('span')); row.appendChild(document.createElement('span')); row.lastChild.className = 'kind';
      if (canTap) {
        box.type = row.type = 'button'; box.addEventListener('click', () => tap(n.key)); row.addEventListener('click', () => tap(n.key));
      }
      row.addEventListener('mouseenter', () => highlight(n.key, true)); row.addEventListener('mouseleave', () => highlight(n.key, false));
      boxes.set(n.key, box); rows.set(n.key, row); $('nodes').appendChild(box); $('tree').appendChild(row);
    }
    const [left, top, right, bottom] = n.bounds;
    const small = right-left < 140 && bottom-top < 95;
    box.className = 'node ' + (canTap?'actionable':'readonly') + (n.selected === true || n.checked === true ? ' is-selected':'') + (n.enabled === false?' is-disabled':'') + (small?' small':'') + (top > height*.8?' top-label':'') + (left > width*.9?' right-label':'');
    box.dataset.key = n.key;
    Object.assign(box.style, {left:(left/width*100)+'%',top:(top/height*100)+'%',width:((right-left)/width*100)+'%',height:((bottom-top)/height*100)+'%'});
    // Scroll regions belong in the action list; overlapping panel-size buttons
    // must not swallow taps on the smaller recognized controls in the canvas.
    box.style.display=n.actions?.includes('scroll')?'none':'';
    box.firstChild.textContent = label(n);
    box.title = [label(n),n.key,n.role, n.source, n.effect, n.enabled == null?'可用状态未核实':null].filter(Boolean).join(' · ');
    box.setAttribute('aria-label', label(n));
    row.className = 'tree-row'; row.firstChild.textContent = label(n); row.lastChild.textContent = n.actions?.includes('scroll')?'滚动 ↕':canTap?'点击 ↗':n.selected?'已选中':'只读';
  });
  if (!nodes.length) {
    $('empty').hidden = false;
    $('empty').querySelector('h3').textContent = '当前页面尚未识别';
    $('empty').querySelector('p').textContent = '实时采集仍在进行；页面稳定或切换到已支持界面后，节点会自动出现。';
  }
  $('node-count').textContent = nodes.length + ' 节点';
  const state = snapshot.state || {};
  $('state-json').textContent = JSON.stringify(state, null, 2);
  $('state-summary').replaceChildren();
  const facts = [['页面', snapshot.page], ['可点击', nodes.filter(actionable).length + ' 个'], ['状态组', Object.keys(state).join(' / ') || '无']];
  facts.forEach(([key, value]) => {const row = document.createElement('div'); row.className='stat'; const name=document.createElement('span'), val=document.createElement('strong'); name.textContent=key;val.textContent=value;row.append(name,val);$('state-summary').appendChild(row);});
}
function paintState(next) {
  data = next; serverReceived = performance.now();
  $('connection').className = 'status ' + next.mode; $('connection').lastChild.textContent = statusNames[next.mode] || next.mode;
  $('connect').disabled = ['connected','connecting','locking'].includes(next.mode);
  $('connect').textContent = next.mode === 'connecting' ? '正在连接…' : next.mode === 'locked' ? '重新连接' : '连接平板';
  $('lock').disabled = !['connected','connecting'].includes(next.mode);
  if (!clicking) note(next.message);
  if (pointerHeld || clicking) pending = next.snapshot;
  else render(next.snapshot);
  $('frame-meta').textContent = next.snapshot ? '实时观测 · ' + (next.frame_age_ms/1000).toFixed(1) + ' 秒前' : '采集已停止';
  countdown();
}
async function poll() {
  if (pollBusy) return;
  pollBusy = true;
  try {
    const response = await fetch('/api/state');
    if (!response.ok) throw new Error('服务不可达');
    paintState(await response.json());
  } catch (error) {
    note('本地服务连接中断：' + error.message);
    $('connection').className='status error'; $('connection').lastChild.textContent='服务断开';
    if (data) data.mode='error';
    render(null); $('connect').disabled=true; $('lock').disabled=true;
  } finally { pollBusy = false; }
}
function countdown() {
  const active = ['connected','connecting'].includes(data?.mode);
  const remaining = active ? Math.max(0, data.remaining_seconds - (performance.now()-serverReceived)/1000) : 0;
  $('seconds').textContent = active ? Math.ceil(remaining) : '—';
  $('idle-bar').style.width = (remaining/60*100) + '%';
  $('idle-bar').style.background = remaining < 15 ? '#e4bf76' : '#84baf4';
}
function activity(event) {
  if (!event.isTrusted || data?.mode !== 'connected' || !token) return;
  const now = performance.now();
  if (now-lastActivitySent < 1200) return;
  lastActivitySent = now;
  post('activity').catch(() => {});
}
['pointerdown','pointermove','keydown','wheel'].forEach(name => document.addEventListener(name, activity, {passive:true}));
document.addEventListener('pointerdown', () => {pointerHeld=true;});
function releasePointer() { setTimeout(() => {pointerHeld=false;if(!clicking && pending){render(pending);pending=null;}},0); }
document.addEventListener('pointerup', releasePointer); document.addEventListener('pointercancel', releasePointer);
window.addEventListener('blur', releasePointer);
$('connect').addEventListener('click', async () => {
  $('connect').disabled=true;
  try { token=(await (await fetch('/api/bootstrap')).json()).token; await post('connect'); }
  catch(error){note(error.message);} await poll();
});
$('lock').addEventListener('click', async () => {try {await post('lock');} catch(error){note(error.message);} await poll();});
(async () => {
  try {token=(await (await fetch('/api/bootstrap')).json()).token;} catch(error){note(error.message);}
  await poll(); setInterval(poll, 450); setInterval(countdown, 200);
})();

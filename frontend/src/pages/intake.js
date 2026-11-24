import {heading} from '../components/common/heading.js';
import {records} from '../components/common/records.js';
import {date, esc} from '../utils/dom.js';
import {submit} from '../hooks/submit.js';
import {go} from '../router/hash.js';

export function intakePage(state, identity) {
  const current = state.cases.find(row=>row.id===identity);
  if (!current) return heading('分段交册') + '<p class="empty">没有找到该档案。</p>';
  const form = state.session.role==='operator' ? `<form id="chunk-form">
    <div class="field-grid">
      <label class="field"><span>起始行号</span><input name="start" type="number" min="1" step="1"></label>
      <label class="field data"><span>本段清册记录（JSON 数组）</span><small>馆藏件号 · 馆藏登录号 · 题名</small><textarea name="records" rows="8" spellcheck="false"></textarea></label>
    </div>
    <div class="actions form-actions">
      <button name="mode" value="chunk">提交分段</button>
      <button class="secondary" name="mode" value="seal">提交分段并封单</button>
      <button class="secondary" name="mode" value="finish">仅封单排队</button>
    </div></form>` : '';
  return `${heading('分段交册', current.title)}
    <div id="intake-progress"><p class="note">正在读取收件进度…</p></div>
    ${form}
    <p><a class="secondary" href="#cases/${current.id}">返回档案</a></p>`;
}

function progressView(progress) {
  const segments = progress.segments.map(row=>[row.start_row, row.start_row+row.row_count-1, row.row_count, date(row.created_at)]);
  const sealed = progress.sealed_at
    ? `<p data-testid="sealed">已封单，执行编号 <a href="#runs/${progress.run_id}">${progress.run_id}</a>，后台按收齐的清册排上架顺序单。</p>`
    : `<p class="note">尚未封单。下一段起始行号：${esc(progress.next_row ?? '—')}。</p>`;
  return `<dl class="metrics">
      <div><dt>登记总行数</dt><dd>${esc(progress.total_rows)}</dd></div>
      <div><dt>已收行数</dt><dd>${esc(progress.received_rows)}</dd></div>
      <div><dt>已收段数</dt><dd>${esc(progress.segments.length)}</dd></div>
    </dl>${sealed}${records(['起始行号','结束行号','行数','收件时间'], segments, '尚未收到分段。')}`;
}

export function bindIntake(state, api, identity, fail) {
  const box = document.getElementById('intake-progress');
  const form = document.getElementById('chunk-form');
  async function render() {
    const progress = await api(`/cases/${identity}/intake`);
    box.innerHTML = progressView(progress);
    if (form) {
      if (progress.sealed_at) form.remove();
      else if (progress.next_row) form.elements.start.value = progress.next_row;
    }
  }
  render().catch(fail);
  if (!form) return;
  const report = error=>{ render().catch(()=>{}); fail(error); };
  submit('chunk-form', async data=>{
    const mode = data.get('mode');
    let body = {};
    if (mode !== 'finish') {
      const start = Number(data.get('start'));
      if (!Number.isInteger(start) || start < 1) throw new Error('请填写不小于 1 的起始行号。');
      let list;
      try { list = JSON.parse(data.get('records') || 'null'); }
      catch { throw new Error('本段清册记录需要是 JSON 数组。'); }
      if (!Array.isArray(list) || !list.length) throw new Error('本段清册记录需要是非空数组。');
      body = {start, records: list};
    }
    if (mode === 'chunk') {
      await api(`/cases/${identity}/chunks`, {method:'POST', data:body});
      form.elements.records.value = '';
      await render();
      return;
    }
    const run = await api(`/cases/${identity}/seal`, {method:'POST', data:body});
    go(`runs/${run.id}`);
  }, report);
}

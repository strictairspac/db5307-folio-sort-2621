import {heading} from '../components/common/heading.js';
import {fields, readFields} from '../components/fields.js';
import {topic} from '../constants/project.js';
import {esc} from '../utils/dom.js';
import {submit} from '../hooks/submit.js';
import {go} from '../router/hash.js';

export function editorPage(state, identity) {
  if (state.session.role!=='operator') return heading(topic.modules[1], '经办员可以建立并提交业务档案。');
  const original = state.cases.find(row=>row.id===identity);
  const payload = original?.payload || state.spec.sample;
  state.draft = payload;
  const segmented = payload.records===undefined;
  return `${heading(topic.modules[1], state.spec.guidance)}
    <form id="case-form"><label class="field title-field"><span>档案名称</span><input name="title" required maxlength="120" value="${esc((original?.title || state.spec.name) + ' · 复核')}" /></label>
    <label class="field"><span>交册方式</span><select id="intake-mode">
      <option value="once" ${segmented?'':'selected'}>整册一次提交</option>
      <option value="segmented" ${segmented?'selected':''}>分段交册（先登记总行数）</option>
    </select></label>
    <div class="field-grid" id="payload-fields">${fields(payload, state.spec.field_labels)}</div><div class="actions form-actions"><button id="case-submit">${segmented?'保存并登记':'保存并提交执行'}</button><a class="secondary" href="#cases">返回档案</a></div></form>`;
}

export function bindEditor(state, api, fail) {
  const mode = document.getElementById('intake-mode');
  mode?.addEventListener('change', ()=>{
    state.draft = mode.value==='segmented' ? state.spec.intake_sample : state.spec.sample;
    document.getElementById('payload-fields').innerHTML = fields(state.draft, state.spec.field_labels);
    document.getElementById('case-submit').textContent = mode.value==='segmented' ? '保存并登记' : '保存并提交执行';
  });
  submit('case-form', async data=>{
    const payload = readFields(state.draft, state.spec.field_labels);
    const draft = await api('/cases', {method:'POST', data:{title:data.get('title'), payload}});
    if (payload.records===undefined) { go(`intake/${draft.id}`); return; }
    try {
      const run = await api(`/cases/${draft.id}/runs`, {method:'POST'});
      go(`runs/${run.id}`);
    } catch (error) {
      go(`cases/${draft.id}`);
      fail(new Error(`档案已保存。提交执行失败：${error.message}`));
    }
  }, fail);
}

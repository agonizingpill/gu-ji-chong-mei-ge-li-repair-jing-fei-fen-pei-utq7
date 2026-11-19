import {store} from '../stores/workspace.js';import {folioOptions,folioName} from '../components/folio-index.js';import {ledger,field,input,select,badge} from '../components/ledger.js';import {esc,date} from '../utils/format.js';import {bindForm,num,request} from '../utils/forms.js';import {levels} from '../constants/enums.js';
const itemState={waiting:'等位待搬',moved:'已搬入新柜',cancelled:'已取消'};
function cabinetName(d,id){return esc(d.cabinets.find(c=>c.id===id)?.code||'—');}
function renderPlans(d){
  if(!d.relocations?.length)return '<p class="hint">暂无漏水停用与搬柜安排。</p>';
  return d.relocations.slice().reverse().map(p=>{
    const items=d.relocation_items.filter(i=>i.relocation_id===p.id);
    return `<article class="relocation-card"><header><h3>停用 ${cabinetName(d,p.source_cabinet_id)} 的搬柜方案 #${p.id}</h3><span>${badge(p.status==='completed'?'已全部搬完':'执行中',p.status==='completed'?'good':'medium')} <small>${date(p.created_at)}</small></span></header>${ledger(['卷册','决策树分级','目标柜位','状态','说明'],items.map(i=>[folioName(d,i.accession_id),badge(levels[i.risk_level]||'待测量',i.risk_level||''),i.target_cabinet_id?cabinetName(d,i.target_cabinet_id):'未安排',badge(itemState[i.status],i.status==='moved'?'good':i.status==='cancelled'?'':'high'),esc(i.reason||'—')]),'方案内暂无册件。')}${p.status!=='completed'?`<form class="relocation-run" data-id="${p.id}"><button>确认搬柜 · 按当前柜位执行</button><p class="hint">并发入柜占用空位时会重新安排，已搬册不会重复搬动。</p></form>`:''}</article>`;
  }).join('');
}
export function render(){
  const d=store.data;
  return `<h2>隔离柜占位与漏水停用</h2><p class="intro">漏水柜登记停用后不再接收新册；系统按各册最新测量运行决策树分级，先搬高风险册、再搬其余册，高低风险不同柜，没合适柜位的留原柜等位。</p>
  <div class="cabinet-wall">${d.cabinets.map(c=>{const occupied=d.isolations.filter(i=>i.cabinet_id===c.id&&i.active);return `<section class="cabinet ${c.active?'':'retired'}"><header><b>${esc(c.code)}</b><span>${c.active?`${occupied.length} / ${c.capacity} 位`:badge('漏水停用','high')}</span></header><div class="slots">${Array.from({length:c.capacity},(_,i)=>`<div class="slot ${occupied[i]?'occupied':''}">${occupied[i]?folioName(d,occupied[i].accession_id):c.active?'空置 · 可入柜':'停用 · 停止入柜'}</div>`).join('')}</div></section>`;}).join('')}</div>
  <div class="forms-two">
    <form id="admit"><h3>办理入柜</h3>${field('卷册',select('accession_id',folioOptions(d)))}${field('隔离柜',select('cabinet_id',d.cabinets.filter(c=>c.active).map(c=>`<option value="${c.id}">${esc(c.code)} · 容量${c.capacity}</option>`).join('')))}<button>锁定柜位</button></form>
    <form id="decommission"><h3>漏水登记停用 · 主管</h3>${field('隔离柜',select('cabinet_id',d.cabinets.filter(c=>c.active).map(c=>`<option value="${c.id}">${esc(c.code)} · 现有 ${d.isolations.filter(i=>i.cabinet_id===c.id&&i.active).length} 册</option>`).join('')))}<button>登记停用并编排搬柜</button><p class="hint">停用即按最新测量重新分级，生成搬柜方案；执行前不会移动册件。</p></form>
  </div>
  <h3>搬柜方案与确认</h3><div class="plan-roll">${renderPlans(d)}</div>
  <h3>还在等位的卷册</h3>${ledger(['卷册','当前所在柜','分级','等位原因','所属方案'],d.relocation_items.filter(i=>i.status==='waiting').map(i=>[folioName(d,i.accession_id),cabinetName(d,d.isolations.find(s=>s.accession_id===i.accession_id&&s.active)?.cabinet_id),badge(levels[i.risk_level]||'待测量',i.risk_level||''),esc(i.reason),esc('#'+i.relocation_id)]),'当前没有等位卷册；空出合规柜位后可重新确认搬柜。')}
  <h3>入柜登记簿</h3>${ledger(['卷册','柜位','入柜时间','交接'],d.isolations.map(i=>[folioName(d,i.accession_id),cabinetName(d,i.cabinet_id),date(i.entered),badge(i.active?'在柜':'已出柜',i.active?'':'good')]))}`;
}
export function bind(r){
  bindForm('admit',d=>request('/isolations',num(d,'accession_id','cabinet_id')),r);
  bindForm('decommission',d=>request('/cabinets/'+d.cabinet_id+'/decommission',num(d,'cabinet_id')),r);
  document.querySelectorAll('form.relocation-run').forEach(form=>bindForm(form,()=>request('/relocations/execute',{relocation_id:Number(form.dataset.id)}),r));
}

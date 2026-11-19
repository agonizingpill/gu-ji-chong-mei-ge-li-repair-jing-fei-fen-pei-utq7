import {esc} from '../utils/format.js';import {folioStates} from '../constants/enums.js';
export function folioOptions(data){return data.accessions.map(a=>`<option value="${a.id}">${esc(a.code)} · ${esc(a.title)}</option>`).join('');}
export function folioName(data,id){const a=data.accessions.find(v=>v.id===id);return a?esc(a.title):'未知卷册';}
export function folioIndex(data){return `<aside class="folio-index"><span class="eyebrow">馆藏卷宗 / ${data.accessions.length}</span>${data.accessions.map(a=>`<div class="index-entry"><b>${esc(a.title)}</b><small>${esc(a.code)}</small><em>${folioStates[a.status]}</em></div>`).join('')}</aside>`;}

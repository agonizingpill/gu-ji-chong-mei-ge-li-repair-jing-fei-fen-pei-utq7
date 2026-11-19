import {esc} from '../utils/format.js';
export function ledger(headers,rows,empty='暂无记录；请先完成左侧登记。'){return `<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}" class="empty">${esc(empty)}</td></tr>`}</tbody></table></div>`;}
export const field=(label,input)=>`<label>${label}${input}</label>`;
export const input=(name,type='text',value='',extra='')=>`<input name="${name}" type="${type}" value="${esc(value)}" ${extra} required>`;
export const select=(name,options)=>`<select name="${name}" required>${options}</select>`;
export const badge=(text,kind='')=>`<span class="badge ${kind}">${esc(text)}</span>`;

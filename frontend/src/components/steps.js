import {esc} from '../utils/format.js';
export function stepTimeline(steps){return `<ol class="timeline">${steps.map(s=>`<li class="${s.done?'done':''}"><span>${s.position.toString().padStart(2,'0')}</span><div><b>${esc(s.name)}</b><small>${s.depends_on?'依赖工序 #'+s.depends_on:'首道工序'} · ${s.done?esc(s.evidence):'等待施工签证'} · #${s.id}</small></div></li>`).join('')}</ol>`;}

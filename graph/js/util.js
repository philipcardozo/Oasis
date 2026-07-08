// Pure formatting/text helpers — no shared state, no DOM.
export const fmtBn=v=> v>=1000?`$${(v/1000).toFixed(1)}T`:(v>=10?`$${Math.round(v)}B`:`$${v.toFixed(1)}B`);
export const fmtPrice=v=> Number.isFinite(Number(v))?`$${Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`:"—";
export const fmtSignedMoney=v=>{ const n=Number(v); return Number.isFinite(n)?`${n>=0?"+":"-"}$${Math.abs(n).toFixed(2)}`:"—"; };
export const fmtPct=v=>{ const n=Number(v); return Number.isFinite(n)?`${n>=0?"+":""}${n.toFixed(2)}%`:"—"; };
export const yearOf=v=>{ const m=String(v||"").match(/\d{4}/); return m?Number(m[0]):null; };
export const esc=v=>String(v??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));
export const jsq=v=>esc(JSON.stringify(String(v??"")));
export const normText=v=>String(v??"").normalize("NFKD").replace(/[̀-ͯ]/g,"").toLowerCase().replace(/[^a-z0-9]+/g," ").trim();

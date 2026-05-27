#!/usr/bin/env python3
"""flows.json を読み込んで workflows.html を生成する（ビルドステップ不要・単一HTML）。

使い方:  python gen_workflows.py
- flows.json と同じディレクトリに workflows.html を出力。
- JSON は <script type="application/json" id="workflow-data"> に直接埋め込むため
  file:// 直開きでも動く（fetch 不要）。外部ライブラリ非依存（素 SVG + バニラ JS）。
"""

import json
import pathlib

HERE = pathlib.Path(__file__).parent
FLOWS = HERE / "flows.json"
OUT = HERE / "workflows.html"

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>realtime-bpm-midi-sync — Workflows</title>
<style>
:root{
  --bg:#0c1117; --bg-2:#11171f; --panel:#161d27; --line:#2a3340;
  --text:#d6dde6; --muted:#8a94a3;
  --edge:#2c3441; --edge-active:#ffd166; --edge-active-glow:rgba(255,209,102,0.55);
  --anno-h:300px;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{
  background:var(--bg); color:var(--text);
  font-family:-apple-system,"Segoe UI","Hiragino Sans","Yu Gothic UI",sans-serif;
  overflow:hidden;
}
#app{
  display:grid; height:100vh;
  grid-template-columns:320px 1fr;
  grid-template-rows:auto 1fr 6px var(--anno-h);
  grid-template-areas:"header header" "sidebar canvas" "sidebar resizer" "sidebar annotations";
}
header{grid-area:header; padding:12px 18px; border-bottom:1px solid var(--line); background:var(--bg-2)}
header h1{margin:0; font-size:16px; letter-spacing:.5px}
header .path{font-size:11px; color:var(--muted); margin-top:2px}
header .hint{font-size:11px; color:var(--muted); margin-top:4px}
header .hint b{color:var(--edge-active)}

#sidebar{grid-area:sidebar; background:var(--bg-2); border-right:1px solid var(--line);
  overflow-y:auto; padding:12px}
.flow-btn{display:flex; gap:8px; align-items:flex-start; width:100%; text-align:left;
  background:var(--panel); color:var(--text); border:1px solid var(--line); border-radius:8px;
  padding:8px 10px; margin-bottom:7px; cursor:pointer; font-size:12.5px; line-height:1.3}
.flow-btn:hover{border-color:#3c4858}
.flow-btn.active{border-color:var(--edge-active); box-shadow:0 0 0 1px var(--edge-active) inset}
.flow-btn .ic{font-size:15px; flex:0 0 auto}
.flow-btn .nm{font-weight:600}
.flow-btn .sb{color:var(--muted); font-size:11px}
#legend{margin-top:14px; border-top:1px solid var(--line); padding-top:10px}
#legend .lg{display:flex; align-items:center; gap:8px; font-size:11.5px; margin:5px 0; color:var(--muted)}
#legend .sw{width:14px; height:14px; border-radius:4px; border:1.5px solid}
#reset{margin-top:12px; width:100%; padding:7px; border-radius:8px; cursor:pointer;
  background:var(--panel); color:var(--text); border:1px solid var(--line); font-size:12px}
#reset:hover{border-color:var(--edge-active)}

#canvas-wrap{grid-area:canvas; position:relative; overflow:hidden; background:
  radial-gradient(1200px 600px at 70% -10%, #131b25 0%, var(--bg) 60%)}
svg#canvas{width:100%; height:100%; display:block; cursor:grab}
svg#canvas.panning{cursor:grabbing}

#resizer{grid-area:resizer; background:var(--line); cursor:row-resize}
#resizer:hover{background:var(--edge-active)}

#annotations{grid-area:annotations; background:var(--bg-2); border-top:1px solid var(--line);
  overflow-y:auto; padding:12px 16px}
#annotations h2{margin:0 0 8px; font-size:13px}
#annotations .desc{font-size:12px; color:var(--muted); margin-bottom:10px}
#annotations ol{counter-reset:step; list-style:none; margin:0; padding:0}
#annotations li{counter-increment:step; position:relative; padding:8px 8px 8px 34px;
  margin-bottom:6px; border-radius:8px; border:1px solid transparent; cursor:pointer}
#annotations li::before{content:counter(step); position:absolute; left:6px; top:8px;
  width:20px; height:20px; border-radius:50%; background:var(--panel); border:1px solid var(--line);
  color:var(--edge-active); font-size:11px; font-weight:700; display:flex; align-items:center; justify-content:center}
#annotations li:hover{border-color:#3c4858; background:var(--panel)}
#annotations li.focused{border-color:var(--edge-active)}
#annotations li .fromto{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px; color:var(--text)}
#annotations li .passes{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:11.5px;
  background:var(--panel); border-left:2px solid var(--edge-active); padding:4px 8px; margin:5px 0; border-radius:0 6px 6px 0; color:#e7d9a8}
#annotations li .note{font-size:11.5px; color:var(--muted)}

#tooltip{position:fixed; z-index:50; pointer-events:none; max-width:340px; display:none;
  background:rgba(14,20,28,0.97); border:1px solid var(--edge-active); border-radius:8px;
  padding:9px 11px; font-size:12px; backdrop-filter:blur(6px); box-shadow:0 8px 30px rgba(0,0,0,.5)}
#tooltip .tt-flow{color:var(--edge-active); font-weight:700; margin-bottom:4px}
#tooltip .tt-ft{font-family:ui-monospace,Consolas,monospace; font-size:11px; color:var(--text); margin:3px 0}
#tooltip .tt-chip{display:inline-block; background:var(--panel); border:1px solid var(--line); border-radius:5px; padding:1px 6px; margin:1px}
#tooltip .tt-pass{font-family:ui-monospace,Consolas,monospace; font-size:11px; background:#0d1218;
  border-left:2px solid var(--edge-active); padding:3px 7px; border-radius:0 5px 5px 0; margin:4px 0; color:#e7d9a8; white-space:pre-wrap}
#tooltip .tt-note{color:var(--muted); font-size:11px}
#tooltip .tt-div{border-top:1px dashed var(--line); margin:6px 0}

/* ----- nodes / edges ----- */
.node rect{filter:drop-shadow(0 3px 6px rgba(0,0,0,.45))}
.node .ttl{font-size:12px; font-weight:700; fill:var(--text)}
.node .sub{font-size:10.5px; fill:var(--muted)}
.node.dim{opacity:.18}
.node.in-flow rect{stroke-width:2.5px}
.node.endpoint rect{stroke-width:3px; animation:node-glow 1.1s ease-in-out infinite}

.edge{fill:none; stroke:var(--edge); stroke-width:2px}
.edge.dim{opacity:.12}
.edge.in-flow{stroke:var(--edge-active); filter:drop-shadow(0 0 4px var(--edge-active-glow))}
.edge.focused-edge{animation:edge-pulse 1.1s ease-in-out infinite}

.col-head{fill:var(--muted); font-size:12px; letter-spacing:3px; font-weight:600; text-anchor:middle}
.col-div{stroke:var(--line); stroke-dasharray:3,5}

/* ----- badges ----- */
.edge-step-badge{cursor:pointer}
.edge-step-hit{fill:rgba(0,0,0,0.001)}
.edge-step-pill{fill:var(--panel); stroke:var(--edge-active); stroke-width:1.3px}
.edge-step-badge text{fill:var(--edge-active); font-size:11px; font-weight:700; text-anchor:middle; dominant-baseline:central; pointer-events:none}
.edge-step-halo{fill:none; stroke:var(--edge-active); opacity:0}
.edge-tether{stroke:var(--edge-active); stroke-width:1; stroke-dasharray:2,3; opacity:.5}
.edge-step-badge:hover .edge-step-pill{fill:#22303e}
.edge-step-badge.focused .edge-step-pill{fill:var(--edge-active); stroke:#fff8d6}
.edge-step-badge.focused text{fill:#1a1100}
.edge-step-badge.focused .edge-step-scale{animation:pulse .9s ease-in-out infinite}
.edge-step-badge.focused .edge-step-halo{animation:halo-burst 1.3s ease-out infinite}

@keyframes pulse{
  0%,100%{transform:scale(1); filter:drop-shadow(0 0 2px #fff) drop-shadow(0 0 6px var(--edge-active)) drop-shadow(0 0 12px var(--edge-active-glow))}
  50%{transform:scale(1.42); filter:drop-shadow(0 0 4px #fff) drop-shadow(0 0 10px var(--edge-active)) drop-shadow(0 0 20px var(--edge-active-glow))}
}
@keyframes halo-burst{
  0%{transform:scale(.55); opacity:.85}
  100%{transform:scale(3); opacity:0}
}
@keyframes edge-pulse{
  0%,100%{stroke:var(--edge-active); stroke-width:2.8px; filter:drop-shadow(0 0 4px var(--edge-active-glow))}
  50%{stroke:#fff8d6; stroke-width:4.2px; filter:drop-shadow(0 0 9px var(--edge-active))}
}
@keyframes node-glow{
  0%,100%{filter:drop-shadow(0 0 4px var(--edge-active-glow))}
  50%{filter:drop-shadow(0 0 11px #fff)}
}
@keyframes anno-flash{
  0%{background:rgba(255,209,102,.55)}
  100%{background:rgba(255,209,102,.08)}
}
#annotations li.flash{animation:anno-flash 1.2s ease-out}
.edge-step-scale{transform-origin:center; transform-box:fill-box}
.edge-step-halo{transform-origin:center; transform-box:fill-box}
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>realtime-bpm-midi-sync — ワークフロー</h1>
    <div class="path">docs/workflows.html ・ 生ドラム BPM 検出 → MIDI クロック同期</div>
    <div class="hint">左の<b>フロー</b>を選択 / バッジ・注釈クリックで<b>ステップ強調</b> / ホイール=ズーム ドラッグ=パン / <b>1-9 0</b>=フロー <b>F</b>=全体 <b>Esc</b>=解除</div>
  </header>
  <div id="sidebar">
    <div id="flow-list"></div>
    <div id="legend"></div>
    <button id="reset">全体表示にリセット (F)</button>
  </div>
  <div id="canvas-wrap">
    <svg id="canvas" xmlns="http://www.w3.org/2000/svg"></svg>
  </div>
  <div id="resizer"></div>
  <div id="annotations">
    <h2 id="anno-title">フローを選択してください</h2>
    <div class="desc" id="anno-desc"></div>
    <ol id="anno-list"></ol>
  </div>
</div>
<div id="tooltip"></div>

<script type="application/json" id="workflow-data">
__FLOWS_JSON__
</script>

<script>
"use strict";
const SVGNS="http://www.w3.org/2000/svg";
const DATA=JSON.parse(document.getElementById("workflow-data").textContent);
const VB=DATA.viewBox;
const nodeById={}; DATA.nodes.forEach(n=>nodeById[n.id]=n);
const groupById={}; DATA.groups.forEach(g=>groupById[g.id]=g);

const svg=document.getElementById("canvas");
let view={x:0,y:0,w:VB.w,h:VB.h};
function applyView(){ svg.setAttribute("viewBox",`${view.x} ${view.y} ${view.w} ${view.h}`); }
applyView();

// ---- layers (順序が最重要: defs → col → edge → node → badge) ----
const defs=mk("defs");
const colLayer=mk("g",{class:"col-layer"});
const edgeLayer=mk("g",{class:"edge-layer"});
const nodeLayer=mk("g",{class:"node-layer"});
const badgeLayer=mk("g",{class:"badge-layer"});
svg.append(defs,colLayer,edgeLayer,nodeLayer,badgeLayer);

// arrow markers
defs.innerHTML=`
<marker id="arr" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto" markerUnits="userSpaceOnUse">
  <path d="M0,0 L7,3 L0,6 Z" fill="var(--edge)"></path></marker>
<marker id="arr-a" markerWidth="13" markerHeight="13" refX="8" refY="4" orient="auto" markerUnits="userSpaceOnUse">
  <path d="M0,0 L9,4 L0,8 Z" fill="var(--edge-active)"></path></marker>`;

function mk(tag,attrs){const e=document.createElementNS(SVGNS,tag);
  if(attrs)for(const k in attrs)e.setAttribute(k,attrs[k]); return e;}

// ---- columns ----
DATA.columns.forEach(c=>{
  const t=mk("text",{class:"col-head",x:c.x,y:26}); t.textContent=c.label; colLayer.appendChild(t);
  if(c.divider!=null && c.divider<VB.w){
    colLayer.appendChild(mk("line",{class:"col-div",x1:c.divider,y1:38,x2:c.divider,y2:VB.h-10}));
  }
});

// ---- nodes ----
function nodeCenter(n){return {x:n.x+n.w/2,y:n.y+n.h/2};}
const nodeEls={};
DATA.nodes.forEach(n=>{
  const g=groupById[n.group]||{stroke:"#888",fill:"#222",sub:"#aaa"};
  const el=mk("g",{class:"node","data-id":n.id});
  const r=mk("rect",{x:n.x,y:n.y,width:n.w,height:n.h,rx:8,fill:g.fill,stroke:g.stroke});
  const ttl=mk("text",{class:"ttl",x:n.x+12,y:n.y+22}); ttl.textContent=n.title;
  const sub=mk("text",{class:"sub",x:n.x+12,y:n.y+39}); sub.textContent=n.subtitle||"";
  el.append(r,ttl,sub); nodeLayer.appendChild(el); nodeEls[n.id]=el;
  el.addEventListener("mouseover",e=>{ if(activeFlowId)return; showNodeTip(n,e); });
  el.addEventListener("mousemove",e=>{ if(activeFlowId)return; moveTip(e); });
  el.addEventListener("mouseout",()=>hideTip());
});

// ---- unique edges + bidirectional lane offset ----
const edgeMap={}; // key "from|to"
DATA.flows.forEach(f=>f.steps.forEach((s,i)=>{
  const key=s.from+"|"+s.to;
  (edgeMap[key]=edgeMap[key]||{from:s.from,to:s.to,steps:[]}).steps.push({flow:f,idx:i});
}));
const edges=Object.values(edgeMap);
const LANE=19;
edges.forEach(e=>{
  const rev=edgeMap[e.to+"|"+e.from];
  if(rev){ e.lane=(e.from<e.to)?LANE:-LANE; } else { e.lane=0; }
});

function isVertical(a,b){ return Math.abs(nodeCenter(a).x-nodeCenter(b).x)<60; }

function edgePath(e){
  const A=nodeById[e.from], B=nodeById[e.to];
  const ca=nodeCenter(A), cb=nodeCenter(B);
  let x1,y1,x2,y2,cp1x,cp1y,cp2x,cp2y;
  if(isVertical(A,B)){
    // 縦: 上下端に接続、lane は x 方向
    const down=cb.y>ca.y;
    x1=ca.x; y1=down?A.y+A.h:A.y; x2=cb.x; y2=down?B.y:B.y+B.h;
    const my=(y1+y2)/2;
    cp1x=x1+e.lane; cp1y=my; cp2x=x2+e.lane; cp2y=my;
  } else {
    // 横: 左右端に接続、lane は y 方向
    const right=cb.x>ca.x;
    x1=right?A.x+A.w:A.x; y1=ca.y; x2=right?B.x:B.x+B.w; y2=cb.y;
    const mx=(x1+x2)/2;
    cp1x=mx; cp1y=y1+e.lane; cp2x=mx; cp2y=y2+e.lane;
  }
  return `M ${x1} ${y1} C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${x2} ${y2}`;
}

edges.forEach(e=>{
  e.pathStr=edgePath(e);
  e.el=mk("path",{class:"edge",d:e.pathStr,"marker-end":"url(#arr)"});
  edgeLayer.appendChild(e.el);
});

// ====================== flow rendering / badges ======================
let activeFlowId=null;
let focused=null; // {flowId, stepIdx}
const flowById={}; DATA.flows.forEach(f=>flowById[f.id]=f);

const BADGE_OFFS=[0.50,0.44,0.56,0.38,0.62,0.32,0.68,0.26,0.74,0.20,0.80,0.15,0.85,0.10,0.90];
const placedBadges=[]; // {x,y,w,h}

function nodeRects(){ return DATA.nodes.map(n=>({x:n.x,y:n.y,w:n.w,h:n.h})); }

function rectOverlap(a,b,m){ m=m||0;
  return !(a.x+a.w+m<b.x || b.x+b.w+m<a.x || a.y+a.h+m<b.y || b.y+b.h+m<a.y); }

function ellipseDist(a,b){ const dx=(a.x-b.x)/((a.w+b.w)/2), dy=(a.y-b.y)/((a.h+b.h)/2);
  return Math.hypot(dx,dy); }

function placeBadge(pathEl, bw, bh){
  const L=pathEl.getTotalLength();
  const nrects=nodeRects();
  let best=null, bestScore=-1e9;
  for(const t of BADGE_OFFS){
    const p=pathEl.getPointAtLength(L*t);
    const cand={x:p.x,y:p.y,w:bw,h:bh};
    let score=0;
    for(const pb of placedBadges){ const d=ellipseDist(cand,pb); if(d<1.05) score-=(1.05-d)*4; }
    for(const nr of nrects){ if(rectOverlap(cand,nr,4)) score-=3.5; }
    score-=Math.abs(t-0.5)*0.3;
    if(score>bestScore){ bestScore=score; best={x:p.x,y:p.y,len:L*t}; }
  }
  // escape: node bbox に重なるなら path 上を歩いて脱出
  let cand={x:best.x,y:best.y,w:bw,h:bh};
  let inNode=nrects.some(nr=>rectOverlap(cand,nr,4));
  if(inNode){
    for(let step=8; step<=L*0.45 && inNode; step+=8){
      for(const dir of [1,-1]){
        const len=Math.min(L-1,Math.max(1,best.len+dir*step));
        const p=pathEl.getPointAtLength(len); cand={x:p.x,y:p.y,w:bw,h:bh};
        if(!nrects.some(nr=>rectOverlap(cand,nr,4))){ best={x:p.x,y:p.y,len}; inNode=false; break; }
      }
    }
  }
  return best;
}

function stepLabel(idxs){ // idxs: 1-based step numbers on this edge
  if(idxs.length===1) return ""+idxs[0];
  if(idxs.length<=5) return idxs.join(" · ");
  return `${idxs[0]}–${idxs[idxs.length-1]} (${idxs.length})`;
}

function clearBadges(){ badgeLayer.innerHTML=""; placedBadges.length=0; }

function renderFlow(flowId){
  activeFlowId=flowId; focused=null; clearBadges();
  const flow=flowById[flowId];
  const flowEdges={}; // key -> [stepIdx1based,...]
  const flowNodes=new Set();
  flow.steps.forEach((s,i)=>{ const k=s.from+"|"+s.to; (flowEdges[k]=flowEdges[k]||[]).push(i+1);
    flowNodes.add(s.from); flowNodes.add(s.to); });

  // node states
  DATA.nodes.forEach(n=>{ const el=nodeEls[n.id]; el.classList.remove("dim","in-flow","endpoint");
    if(flowNodes.has(n.id)) el.classList.add("in-flow"); else el.classList.add("dim"); });
  // edge states
  edges.forEach(e=>{ const on=flowEdges[e.from+"|"+e.to]; e.el.classList.remove("dim","in-flow","focused-edge");
    e.el.setAttribute("marker-end", on?"url(#arr-a)":"url(#arr)");
    if(on) e.el.classList.add("in-flow"); else e.el.classList.add("dim"); });

  // badges: マルチステップ→短いパスを先に（midpoint確保）
  const badgeJobs=Object.keys(flowEdges).map(k=>{
    const e=edgeMap[k]; return {e, idxs:flowEdges[k], len:e.el.getTotalLength()};
  }).sort((a,b)=> (b.idxs.length-a.idxs.length) || (a.len-b.len));

  const built=[];
  badgeJobs.forEach(job=>{
    const label=stepLabel(job.idxs);
    const bw=Math.max(22, 12+label.length*7.2), bh=20;
    const pos=placeBadge(job.e.el, bw, bh);
    placedBadges.push({x:pos.x,y:pos.y,w:bw,h:bh});
    built.push({job,label,bw,bh,pos});
  });

  // DOM 描画（ステップ順）
  built.sort((a,b)=>a.job.idxs[0]-b.job.idxs[0]);
  built.forEach(b=>{
    const {job,label,bw,bh,pos}=b;
    // tether（midpoint=path中点 から離れている場合）
    const mid=job.e.el.getPointAtLength(job.e.el.getTotalLength()*0.5);
    if(Math.hypot(mid.x-pos.x,mid.y-pos.y)>26){
      badgeLayer.appendChild(mk("line",{class:"edge-tether",x1:mid.x,y1:mid.y,x2:pos.x,y2:pos.y}));
    }
    const outer=mk("g",{class:"edge-step-badge",transform:`translate(${pos.x},${pos.y})`});
    outer.appendChild(mk("ellipse",{class:"edge-step-halo",cx:0,cy:0,rx:bw/2,ry:bh/2}));
    outer.appendChild(mk("rect",{class:"edge-step-hit",x:-bw/2-8,y:-bh/2-8,width:bw+16,height:bh+16,rx:bh/2}));
    const scale=mk("g",{class:"edge-step-scale"});
    scale.appendChild(mk("rect",{class:"edge-step-pill",x:-bw/2,y:-bh/2,width:bw,height:bh,rx:bh/2}));
    const txt=mk("text"); txt.textContent=label; scale.appendChild(txt);
    outer.appendChild(scale);
    badgeLayer.appendChild(outer);

    let cycle=0;
    outer.addEventListener("mouseover",e=>showStepTip(job,e));
    outer.addEventListener("mousemove",e=>moveTip(e));
    outer.addEventListener("mouseout",e=>{ if(!outer.contains(e.relatedTarget)) hideTip(); });
    outer.addEventListener("click",()=>{
      const stepIdx=job.idxs[cycle%job.idxs.length]-1; cycle++;
      focusStep(flowId, stepIdx, true);
    });
    job.e._outer=outer;   // edgeMap エントリに保持（focusStep が参照）
  });

  // sidebar / annotations
  document.querySelectorAll(".flow-btn").forEach(b=>b.classList.toggle("active", b.dataset.id===flowId));
  buildAnnotations(flow);
  fitTo([...flowNodes]);
  hideTip();
}

// ---- focus (5層 PIKAPIKA) ----
function clearFocusVisual(){
  document.querySelectorAll(".edge-step-badge.focused").forEach(b=>b.classList.remove("focused"));
  edges.forEach(e=>e.el.classList.remove("focused-edge"));
  DATA.nodes.forEach(n=>nodeEls[n.id].classList.remove("endpoint"));
  document.querySelectorAll("#anno-list li.focused").forEach(li=>li.classList.remove("focused"));
}
function focusStep(flowId, stepIdx, scroll){
  if(activeFlowId!==flowId) renderFlow(flowId);
  focused={flowId,stepIdx};
  clearFocusVisual();
  const flow=flowById[flowId]; const s=flow.steps[stepIdx];
  // 1+2 badge (edge上で該当stepを含むバッジ)
  const e=edgeMap[s.from+"|"+s.to];
  if(e&&e._outer) e._outer.classList.add("focused");
  // 4 edge pulse
  if(e) e.el.classList.add("focused-edge");
  // 5 endpoints
  nodeEls[s.from] && nodeEls[s.from].classList.add("endpoint");
  nodeEls[s.to] && nodeEls[s.to].classList.add("endpoint");
  // 6 anno flash（再クリックでも再生: remove→reflow→add）
  const li=document.querySelector(`#anno-list li[data-idx="${stepIdx}"]`);
  if(li){ li.classList.add("focused"); li.classList.remove("flash"); void li.offsetWidth; li.classList.add("flash");
    if(scroll) li.scrollIntoView({block:"nearest",behavior:"smooth"}); }
  // pan して該当エッジ中点を中央付近へ
  if(e){ const m=e.el.getPointAtLength(e.el.getTotalLength()*0.5); panTo(m.x,m.y); }
}

// ---- annotations ----
function buildAnnotations(flow){
  document.getElementById("anno-title").textContent=`${flow.icon} ${flow.name}`;
  document.getElementById("anno-desc").textContent=flow.description||"";
  const ol=document.getElementById("anno-list"); ol.innerHTML="";
  flow.steps.forEach((s,i)=>{
    const li=document.createElement("li"); li.dataset.idx=i;
    const A=nodeById[s.from], B=nodeById[s.to];
    li.innerHTML=`<div class="fromto">${esc(A?A.title:s.from)} → ${esc(B?B.title:s.to)}</div>`+
      (s.passes?`<div class="passes">${esc(s.passes)}</div>`:"")+
      (s.note?`<div class="note">${esc(s.note)}</div>`:"");
    li.addEventListener("click",()=>focusStep(flow.id,i,true));
    ol.appendChild(li);
  });
}

// ---- tooltip ----
const tip=document.getElementById("tooltip");
function showStepTip(job,ev){
  const f=flowById[activeFlowId];   // バッジは選択中フローに属する
  let html="";
  job.idxs.forEach((num,k)=>{
    const s=f.steps[num-1];
    if(k>0) html+=`<div class="tt-div"></div>`;
    html+=`<div class="tt-flow">${f.icon} ${esc(f.name)} — step ${num}</div>`;
    html+=`<div class="tt-ft"><span class="tt-chip">${esc(nodeById[s.from]?nodeById[s.from].title:s.from)}</span> → <span class="tt-chip">${esc(nodeById[s.to]?nodeById[s.to].title:s.to)}</span></div>`;
    if(s.passes) html+=`<div class="tt-pass">${esc(s.passes)}</div>`;
    if(s.note) html+=`<div class="tt-note">${esc(s.note)}</div>`;
  });
  tip.innerHTML=html; tip.style.display="block"; moveTip(ev);
}
function showNodeTip(n,ev){
  tip.innerHTML=`<div class="tt-flow">${esc(n.title)}</div><div class="tt-note">${esc(n.subtitle||"")}</div>`;
  tip.style.display="block"; moveTip(ev);
}
function moveTip(ev){
  let x=ev.clientX+16, y=ev.clientY+16;
  const r=tip.getBoundingClientRect();
  if(x+r.width>window.innerWidth) x=ev.clientX-r.width-16;
  if(y+r.height>window.innerHeight) y=ev.clientY-r.height-16;
  tip.style.left=x+"px"; tip.style.top=y+"px";
}
function hideTip(){ tip.style.display="none"; }

// ---- view: fit / pan / zoom ----
function fitTo(ids){
  if(!ids||!ids.length){ view={x:0,y:0,w:VB.w,h:VB.h}; applyView(); return; }
  let minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9;
  ids.forEach(id=>{const n=nodeById[id]; if(!n)return;
    minx=Math.min(minx,n.x); miny=Math.min(miny,n.y); maxx=Math.max(maxx,n.x+n.w); maxy=Math.max(maxy,n.y+n.h);});
  const pad=60; minx-=pad;miny-=pad;maxx+=pad;maxy+=pad;
  let w=maxx-minx, h=maxy-miny;
  const ar=svg.clientWidth/svg.clientHeight;
  if(w/h<ar){ const nw=h*ar; minx-=(nw-w)/2; w=nw; } else { const nh=w/ar; miny-=(nh-h)/2; h=nh; }
  animateView({x:minx,y:miny,w,h});
}
function animateView(target){
  const start={...view}, t0=performance.now(), dur=420;
  function step(t){ const k=Math.min(1,(t-t0)/dur), e=1-Math.pow(1-k,3);
    view={x:start.x+(target.x-start.x)*e, y:start.y+(target.y-start.y)*e,
          w:start.w+(target.w-start.w)*e, h:start.h+(target.h-start.h)*e};
    applyView(); if(k<1) requestAnimationFrame(step); }
  requestAnimationFrame(step);
}
function panTo(cx,cy){ animateView({x:cx-view.w/2, y:cy-view.h/2, w:view.w, h:view.h}); }

svg.addEventListener("wheel",ev=>{ ev.preventDefault();
  const rect=svg.getBoundingClientRect();
  const px=view.x+(ev.clientX-rect.left)/rect.width*view.w;
  const py=view.y+(ev.clientY-rect.top)/rect.height*view.h;
  const f=ev.deltaY<0?0.88:1.137;
  const nw=Math.min(VB.w*2.5,Math.max(180,view.w*f)), nh=nw*view.h/view.w;
  view={x:px-(px-view.x)*nw/view.w, y:py-(py-view.y)*nh/view.h, w:nw, h:nh}; applyView();
},{passive:false});

let pan=null;
svg.addEventListener("mousedown",ev=>{ if(ev.target.closest(".edge-step-badge")||ev.target.closest(".node"))return;
  pan={x:ev.clientX,y:ev.clientY,vx:view.x,vy:view.y}; svg.classList.add("panning"); });
window.addEventListener("mousemove",ev=>{ if(!pan)return;
  const rect=svg.getBoundingClientRect();
  view.x=pan.vx-(ev.clientX-pan.x)/rect.width*view.w;
  view.y=pan.vy-(ev.clientY-pan.y)/rect.height*view.h; applyView(); });
window.addEventListener("mouseup",()=>{ pan=null; svg.classList.remove("panning"); });

// ---- sidebar ----
const flowList=document.getElementById("flow-list");
DATA.flows.forEach(f=>{
  const b=document.createElement("button"); b.className="flow-btn"; b.dataset.id=f.id;
  b.innerHTML=`<span class="ic">${f.icon||"●"}</span><span><span class="nm">${esc(f.name)}</span><br><span class="sb">${esc(f.sub||"")}</span></span>`;
  b.addEventListener("click",()=>renderFlow(f.id));
  flowList.appendChild(b);
});
const legend=document.getElementById("legend");
DATA.groups.forEach(g=>{ const d=document.createElement("div"); d.className="lg";
  d.innerHTML=`<span class="sw" style="border-color:${g.stroke};background:${g.fill}"></span>${esc(g.label)}`;
  legend.appendChild(d); });
document.getElementById("reset").addEventListener("click",resetAll);

function resetAll(){ activeFlowId=null; focused=null; clearBadges(); clearFocusVisual();
  DATA.nodes.forEach(n=>nodeEls[n.id].classList.remove("dim","in-flow","endpoint"));
  edges.forEach(e=>{ e.el.classList.remove("dim","in-flow","focused-edge"); e.el.setAttribute("marker-end","url(#arr)"); });
  document.querySelectorAll(".flow-btn").forEach(b=>b.classList.remove("active"));
  document.getElementById("anno-title").textContent="フローを選択してください";
  document.getElementById("anno-desc").textContent="";
  document.getElementById("anno-list").innerHTML="";
  fitTo(null);
}

// ---- keyboard ----
window.addEventListener("keydown",ev=>{
  const k=ev.key;
  if(k>="1"&&k<="9"){ const i=+k-1; if(DATA.flows[i]) renderFlow(DATA.flows[i].id); }
  else if(k==="0"){ if(DATA.flows[9]) renderFlow(DATA.flows[9].id); }
  else if(k==="f"||k==="F"){ resetAll(); }
  else if(k==="+"||k==="="){ const nw=Math.max(180,view.w*0.85); view={x:view.x+(view.w-nw)/2,y:view.y+(view.h-nw*view.h/view.w)/2,w:nw,h:nw*view.h/view.w}; applyView(); }
  else if(k==="-"||k==="_"){ const nw=Math.min(VB.w*2.5,view.w*1.18); view={x:view.x-(nw-view.w)/2,y:view.y-(nw*view.h/view.w-view.h)/2,w:nw,h:nw*view.h/view.w}; applyView(); }
  else if(k==="Escape"){ if(focused){ focused=null; clearFocusVisual(); } else if(activeFlowId){ resetAll(); } }
});

// ---- resizer ----
const resizer=document.getElementById("resizer");
const SAVED=localStorage.getItem("annoH"); if(SAVED) document.documentElement.style.setProperty("--anno-h",SAVED);
let rz=null;
resizer.addEventListener("mousedown",ev=>{ rz={y:ev.clientY,h:parseInt(getComputedStyle(document.documentElement).getPropertyValue("--anno-h"))}; ev.preventDefault(); });
window.addEventListener("mousemove",ev=>{ if(!rz)return; let h=Math.max(120,Math.min(window.innerHeight-260,rz.h-(ev.clientY-rz.y)));
  document.documentElement.style.setProperty("--anno-h",h+"px"); });
window.addEventListener("mouseup",()=>{ if(rz){ localStorage.setItem("annoH",getComputedStyle(document.documentElement).getPropertyValue("--anno-h").trim()); rz=null; } });

function esc(s){ return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

// 初期表示: 最初のフロー（レイアウト確定後に fit するため rAF 越し）
requestAnimationFrame(()=>{ if(DATA.flows.length) renderFlow(DATA.flows[0].id); });
</script>
</body>
</html>
"""


def main():
    flows_text = FLOWS.read_text(encoding="utf-8")
    # JSON を検証してから（最小化せず）埋め込む
    data = json.loads(flows_text)
    embedded = json.dumps(data, ensure_ascii=False, indent=2)
    html = TEMPLATE.replace("__FLOWS_JSON__", embedded)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  ({len(html)} bytes, {len(data['flows'])} flows, {len(data['nodes'])} nodes)")


if __name__ == "__main__":
    main()

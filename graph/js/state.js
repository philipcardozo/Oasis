// Shared mutable state, DOM refs, static keys and persistence helpers.
// Imported read-only elsewhere; mutate scalars via the set* functions.
import {DUE_DILIGENCE_SOURCES,DATA_LAYER_BY_ID} from "./config.js";

export const SVGNS="http://www.w3.org/2000/svg";
export let SECTORS={},GROUPS={},RELS={},COMPANIES=[],LINKS=[],NEWS={items_by_node:{}},EDGE_CANDIDATES=[],ALIASES={},META={},byId={},adj={},bulkLoaded=false,bulkPromise=null,grid=new Map();
export const sectorOn={},groupOn={},relOn={},kindOn={};
export let selected=null,hovEdge=null,mode="network",rafId=null;
export let networkScope=null;
export let hoverNodeId=null;
export const hoverFrozenIds=new Set();
export let visibleEdgeCache=null,visibleEdgeSet=null,linkedNodeCache=null;
export let hoverFrame=0,pendingHover=null;
export const globe={unknownCount:0};
export let globeSelectionLabel="";
export let map=null,mapReady=false,mapInitPromise=null,mapClusterIds=[],mapLayerEventsBound=false,mapSelectedId=null,mapSelectedSource=null;
export let hoveredFarmId="";
export const mapData={companies:null,securities:null,relationships:null,graphIndex:null,unknown:null};
export let activeRailPanel="",manualSelectedId=null;
export let maxEdgeVal=1,maxNodeVal=1;
export const params=new URLSearchParams(location.search);
export let selfViewId=params.get("self")||"",selfViewNodes=new Set();
if(selfViewId) document.body.classList.add("self-view");

export const svg=document.getElementById("svg"),vp=document.getElementById("viewport");
export const canvas=document.getElementById("canvas"),ctx=canvas.getContext("2d");
export const gEdges=document.getElementById("edges"),gLabels=document.getElementById("edgeLabels"),gNodes=document.getElementById("nodes"),tip=document.getElementById("tip");
export let edgeEls=[],labelEls=[],nodeEls=[],nodeElsById={};
export const asOfInput=document.getElementById("asOf");
export const CURRENT_YEAR=new Date().getFullYear();
asOfInput.max=String(CURRENT_YEAR);
export const HOVER_LINK_CAP=4;
export const VIEW_STATE_KEY="oasis.relationshipGraph.view.v2";
export const PRODUCT_PREF_KEY="oasis.relationshipGraph.productPrefs.v1";
export const MANUAL_LAYER_KEY="oasis.relationshipGraph.manualLayer.v1";
export let restoredView=loadViewState(),restoringView=true,saveViewTimer=0;
if(restoredView.theme==="light"||restoredView.theme==="dark") document.documentElement.setAttribute("data-theme",restoredView.theme);
export const PRODUCT_DEFAULTS={
  engine:{accent:"#ff3045",labels:"major",terrain:true,terrainExaggeration:1.12,nodeScale:1,edgeOpacity:1,motion:true},
  maker:{sections:{counterparties:true,relationships:true,lens:true,candidates:true,market:true,filings:true,research:true,news:true}},
  lens:"company",
  terrainSource:"aws",
  assetGraph:{relationship_type:"",asset_type:"",confidence_min:"0"},
  marketplace:{asset_type:"",location:"",min_price:"",max_price:"",min_acres:"",max_acres:"",min_square_feet:"",max_square_feet:"",zoning:"",listing_status:"active",owner_type:"",risk_max:"",soil_quality_min:"",infrastructure_distance_max:"",view:"cards",sort:"price"},
  dataLayers:{}
};
export let productPrefs=mergePrefs(loadStored(PRODUCT_PREF_KEY,{}));
export let manualLayer=normalizeManualLayer(loadStored(MANUAL_LAYER_KEY,null));
export const dataSourceStatus=Object.fromEntries(DUE_DILIGENCE_SOURCES.map(id=>[id,{state:"not loaded",count:0,error:""}]));
export const dataLayerCounts={};
export let terrainDemStatus={state:"not loaded yet",count:0,error:"",tilejson:null};
export let terrainDemStatusPromise=null;
export let dataQualityPromise=null;
export let dataQualityLast=0;
export let dueDiligenceLoadTimer=0;
export let marketplaceListings=[];
export let selectedEntityAssetFeatures=[];
Object.values(DATA_LAYER_BY_ID).forEach(layer=>{
  if(productPrefs.dataLayers[layer.id]===undefined) productPrefs.dataLayers[layer.id]=!!layer.defaultOn;
});

export function loadViewState(){
  try{ return JSON.parse(localStorage.getItem(VIEW_STATE_KEY)||"{}")||{}; }
  catch(_err){ return {}; }
}
export function cloneJson(v){ return JSON.parse(JSON.stringify(v)); }
export function loadStored(key,fallback){
  try{ return JSON.parse(localStorage.getItem(key)||"null") ?? fallback; }
  catch(_err){ return fallback; }
}
export function mergePrefs(saved={}){
  const out=cloneJson(PRODUCT_DEFAULTS);
  Object.assign(out.engine,saved.engine||{});
  Object.assign(out.maker.sections,saved.maker?.sections||{});
  if(saved.lens) out.lens=saved.lens;
  Object.assign(out.assetGraph,saved.assetGraph||{});
  Object.assign(out.marketplace,saved.marketplace||{});
  Object.assign(out.dataLayers,saved.dataLayers||{});
  return out;
}
export function saveProductPrefs(){
  localStorage.setItem(PRODUCT_PREF_KEY,JSON.stringify(productPrefs));
}
export function emptyManualLayer(){
  const now=new Date().toISOString();
  return {version:1,name:"Local scenario",created_at:now,updated_at:now,nodes:[],edges:[],scenarios:[]};
}
export function normalizeManualLayer(raw){
  const base=emptyManualLayer(),src=raw&&typeof raw==="object"?raw:{};
  return {
    ...base,...src,
    nodes:Array.isArray(src.nodes)?src.nodes.map(n=>({...n,lat:Number(n.lat),lng:Number(n.lng)})):[],
    edges:Array.isArray(src.edges)?src.edges:[],
    scenarios:Array.isArray(src.scenarios)?src.scenarios:[]
  };
}
export function saveManualLayer(){
  manualLayer.updated_at=new Date().toISOString();
  localStorage.setItem(MANUAL_LAYER_KEY,JSON.stringify(manualLayer));
}
export function downloadText(name,text,type="text/plain"){
  const a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([text],{type}));
  a.download=name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),30000);
}
export function savedMode(){
  return ["network","index","globe"].includes(restoredView.mode)?restoredView.mode:"network";
}

// --- setters (imports are read-only across modules; 'assign' prefix avoids clashing with existing setX view fns) ---
export function assignSECTORS(v){ SECTORS=v; return v; }
export function assignGROUPS(v){ GROUPS=v; return v; }
export function assignRELS(v){ RELS=v; return v; }
export function assignCOMPANIES(v){ COMPANIES=v; return v; }
export function assignLINKS(v){ LINKS=v; return v; }
export function assignNEWS(v){ NEWS=v; return v; }
export function assignEDGE_CANDIDATES(v){ EDGE_CANDIDATES=v; return v; }
export function assignALIASES(v){ ALIASES=v; return v; }
export function assignMETA(v){ META=v; return v; }
export function assignById(v){ byId=v; return v; }
export function assignAdj(v){ adj=v; return v; }
export function assignBulkLoaded(v){ bulkLoaded=v; return v; }
export function assignBulkPromise(v){ bulkPromise=v; return v; }
export function assignGrid(v){ grid=v; return v; }
export function assignSelected(v){ selected=v; return v; }
export function assignHovEdge(v){ hovEdge=v; return v; }
export function assignMode(v){ mode=v; return v; }
export function assignRafId(v){ rafId=v; return v; }
export function assignNetworkScope(v){ networkScope=v; return v; }
export function assignHoverNodeId(v){ hoverNodeId=v; return v; }
export function assignVisibleEdgeCache(v){ visibleEdgeCache=v; return v; }
export function assignVisibleEdgeSet(v){ visibleEdgeSet=v; return v; }
export function assignLinkedNodeCache(v){ linkedNodeCache=v; return v; }
export function assignHoverFrame(v){ hoverFrame=v; return v; }
export function assignPendingHover(v){ pendingHover=v; return v; }
export function assignGlobeSelectionLabel(v){ globeSelectionLabel=v; return v; }
export function assignMap(v){ map=v; return v; }
export function assignMapReady(v){ mapReady=v; return v; }
export function assignMapInitPromise(v){ mapInitPromise=v; return v; }
export function assignMapClusterIds(v){ mapClusterIds=v; return v; }
export function assignMapLayerEventsBound(v){ mapLayerEventsBound=v; return v; }
export function assignMapSelectedId(v){ mapSelectedId=v; return v; }
export function assignMapSelectedSource(v){ mapSelectedSource=v; return v; }
export function assignHoveredFarmId(v){ hoveredFarmId=v; return v; }
export function assignActiveRailPanel(v){ activeRailPanel=v; return v; }
export function assignManualSelectedId(v){ manualSelectedId=v; return v; }
export function assignMaxEdgeVal(v){ maxEdgeVal=v; return v; }
export function assignMaxNodeVal(v){ maxNodeVal=v; return v; }
export function assignSelfViewId(v){ selfViewId=v; return v; }
export function assignSelfViewNodes(v){ selfViewNodes=v; return v; }
export function assignEdgeEls(v){ edgeEls=v; return v; }
export function assignLabelEls(v){ labelEls=v; return v; }
export function assignNodeEls(v){ nodeEls=v; return v; }
export function assignNodeElsById(v){ nodeElsById=v; return v; }
export function assignRestoredView(v){ restoredView=v; return v; }
export function assignRestoringView(v){ restoringView=v; return v; }
export function assignSaveViewTimer(v){ saveViewTimer=v; return v; }
export function assignProductPrefs(v){ productPrefs=v; return v; }
export function assignManualLayer(v){ manualLayer=v; return v; }
export function assignTerrainDemStatus(v){ terrainDemStatus=v; return v; }
export function assignTerrainDemStatusPromise(v){ terrainDemStatusPromise=v; return v; }
export function assignDataQualityPromise(v){ dataQualityPromise=v; return v; }
export function assignDataQualityLast(v){ dataQualityLast=v; return v; }
export function assignDueDiligenceLoadTimer(v){ dueDiligenceLoadTimer=v; return v; }
export function assignMarketplaceListings(v){ marketplaceListings=v; return v; }
export function assignSelectedEntityAssetFeatures(v){ selectedEntityAssetFeatures=v; return v; }

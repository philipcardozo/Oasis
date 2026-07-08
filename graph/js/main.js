import {fmtBn,fmtPrice,fmtSignedMoney,fmtPct,yearOf,esc,jsq,normText} from "./util.js";
import {kindMeta,EMPTY_GEOJSON,DUE_DILIGENCE_SOURCES,DUE_DILIGENCE_ENDPOINTS,DATA_ICON_SVG,dl,MARKETPLACE_ASSET_TYPES,DATA_LAYER_PRESETS,DATA_LAYER_BY_ID,DATA_LAYER_OPEN,HQ_CITY_COORDS,COUNTRY_COORDS,COUNTRY_CODES,BAD_HQ_VALUES,EXCHANGE_HQ_VALUES,DRAWER_TYPES} from "./config.js";
import {SECTORS,GROUPS,RELS,COMPANIES,LINKS,NEWS,EDGE_CANDIDATES,ALIASES,META,byId,adj,bulkLoaded,bulkPromise,grid,selected,hovEdge,mode,rafId,networkScope,hoverNodeId,visibleEdgeCache,visibleEdgeSet,linkedNodeCache,hoverFrame,pendingHover,globeSelectionLabel,map,mapReady,mapInitPromise,mapClusterIds,mapLayerEventsBound,mapSelectedId,mapSelectedSource,hoveredFarmId,activeRailPanel,manualSelectedId,maxEdgeVal,maxNodeVal,selfViewId,selfViewNodes,edgeEls,labelEls,nodeEls,nodeElsById,restoredView,restoringView,saveViewTimer,productPrefs,manualLayer,terrainDemStatus,terrainDemStatusPromise,dataQualityPromise,dataQualityLast,dueDiligenceLoadTimer,marketplaceListings,selectedEntityAssetFeatures,SVGNS,sectorOn,groupOn,relOn,kindOn,hoverFrozenIds,globe,mapData,params,svg,vp,canvas,ctx,gEdges,gLabels,gNodes,tip,asOfInput,CURRENT_YEAR,HOVER_LINK_CAP,VIEW_STATE_KEY,PRODUCT_PREF_KEY,MANUAL_LAYER_KEY,PRODUCT_DEFAULTS,dataSourceStatus,dataLayerCounts,loadViewState,cloneJson,loadStored,mergePrefs,saveProductPrefs,emptyManualLayer,normalizeManualLayer,saveManualLayer,downloadText,savedMode,assignSECTORS,assignGROUPS,assignRELS,assignCOMPANIES,assignLINKS,assignNEWS,assignEDGE_CANDIDATES,assignALIASES,assignMETA,assignById,assignAdj,assignBulkLoaded,assignBulkPromise,assignGrid,assignSelected,assignHovEdge,assignMode,assignRafId,assignNetworkScope,assignHoverNodeId,assignVisibleEdgeCache,assignVisibleEdgeSet,assignLinkedNodeCache,assignHoverFrame,assignPendingHover,assignGlobeSelectionLabel,assignMap,assignMapReady,assignMapInitPromise,assignMapClusterIds,assignMapLayerEventsBound,assignMapSelectedId,assignMapSelectedSource,assignHoveredFarmId,assignActiveRailPanel,assignManualSelectedId,assignMaxEdgeVal,assignMaxNodeVal,assignSelfViewId,assignSelfViewNodes,assignEdgeEls,assignLabelEls,assignNodeEls,assignNodeElsById,assignRestoredView,assignRestoringView,assignSaveViewTimer,assignProductPrefs,assignManualLayer,assignTerrainDemStatus,assignTerrainDemStatusPromise,assignDataQualityPromise,assignDataQualityLast,assignDueDiligenceLoadTimer,assignMarketplaceListings,assignSelectedEntityAssetFeatures} from "./state.js";

const activeYear=()=>Math.min(Number(asOfInput.value)||CURRENT_YEAR,CURRENT_YEAR);
function mapCamera(){
  if(!map) return restoredView.map||null;
  const c=map.getCenter();
  return {center:[Number(c.lng.toFixed(6)),Number(c.lat.toFixed(6))],zoom:Number(map.getZoom().toFixed(4)),bearing:Number(map.getBearing().toFixed(2)),pitch:Number(map.getPitch().toFixed(2))};
}
function filterSnapshot(obj){
  return Object.fromEntries(Object.entries(obj).filter(([_k,v])=>!v));
}
function applySavedFilter(obj,saved){
  if(!saved) return;
  Object.keys(obj).forEach(k=>{ if(Object.prototype.hasOwnProperty.call(saved,k)) obj[k]=!!saved[k]; });
}
function applySavedFilters(){
  applySavedFilter(kindOn,restoredView.filters?.kind);
  applySavedFilter(sectorOn,restoredView.filters?.sector);
  applySavedFilter(groupOn,restoredView.filters?.group);
  applySavedFilter(relOn,restoredView.filters?.rel);
}
function modelerStateId(){
  const el=document.getElementById("modeler");
  return el?.classList.contains("show")?el.dataset.id||"":"";
}
function captureViewState(){
  return {
    mode,selected,manualSelectedId,modelerId:modelerStateId(),asOf:activeYear(),
    theme:document.documentElement.getAttribute("data-theme")||"dark",
    svg:{k:Number(k.toFixed(5)),tx:Number(tx.toFixed(2)),ty:Number(ty.toFixed(2))},
    map:mapCamera(),
    filters:{kind:filterSnapshot(kindOn),sector:filterSnapshot(sectorOn),group:filterSnapshot(groupOn),rel:filterSnapshot(relOn)}
  };
}
function saveViewNow(){
  if(restoringView) return;
  try{ localStorage.setItem(VIEW_STATE_KEY,JSON.stringify(captureViewState())); }
  catch(err){ console.warn("view state save skipped",err); }
}
function queueSaveView(){
  if(restoringView) return;
  clearTimeout(saveViewTimer);
  assignSaveViewTimer(setTimeout(saveViewNow,120));
}
function restoreSvgView(){
  const v=restoredView.svg||{};
  if([v.k,v.tx,v.ty].every(Number.isFinite)){
    k=Math.max(.08,Math.min(7,v.k)); tx=v.tx; ty=v.ty; applyView();
  }
}
function syncThemeButton(){
  const light=document.documentElement.getAttribute("data-theme")==="light";
  const tool=document.getElementById("toolThemeBtn");
  if(tool){
    tool.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3 7.2 7.2 0 0 0 21 12.8Z"/></svg><span>${light?"Dark mode":"Light mode"}</span>`;
  }
}
function syncModeButton(){
  const tool=document.getElementById("toolModeBtn");
  const globe=document.getElementById("toolGlobeBtn");
  if(tool){
    tool.textContent=mode==="index"?"Network only":"All entities";
    tool.classList.toggle("active",mode==="index");
  }
  if(globe) globe.classList.toggle("active",mode==="globe");
}
function accentSoft(hex){
  const h=String(hex||"#ff3045").replace("#","");
  const n=parseInt(h.length===3?h.split("").map(x=>x+x).join(""):h,16);
  if(!Number.isFinite(n)) return "rgba(255,48,69,.16)";
  return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},.16)`;
}
function setLayerVisibility(id,visible){
  if(map?.getLayer(id)) map.setLayoutProperty(id,"visibility",visible?"visible":"none");
}
function dataLayerMapIds(layer){
  const ids=layer.mapLayerIds||[`dd-${layer.id}`];
  return layer.source==="marketplace_listings"&&layer.layerType==="fill"?[...ids,`dd-${layer.id}-icon`]:ids;
}
function applyDueDiligenceLayerVisibility(){
  Object.values(DATA_LAYER_BY_ID).forEach(layer=>{
    dataLayerMapIds(layer).forEach(id=>setLayerVisibility(id,!!productPrefs.dataLayers[layer.id]));
  });
  const marketplaceOn=DATA_LAYER_PRESETS.find(p=>p.id==="marketplace")?.layers.some(layer=>productPrefs.dataLayers[layer.id]);
  setLayerVisibility("marketplace-clusters",!!marketplaceOn);
  setLayerVisibility("marketplace-cluster-count",!!marketplaceOn);
  const terrainOn=!!productPrefs.engine.terrain&&(!!productPrefs.dataLayers["relief-hillshade"]||!!productPrefs.dataLayers["relief-terrain"]);
  if(mapReady&&map?.setTerrain&&map.getSource("terrain-dem")) map.setTerrain(terrainOn?{source:"terrain-dem",exaggeration:Number(productPrefs.engine.terrainExaggeration??1.12)}:null);
  updateDueDiligenceSources();
}
function activeDataSources(){
  const sources=new Set();
  Object.values(DATA_LAYER_BY_ID).forEach(layer=>{
    if(layer.id==="relief-terrain"||layer.id==="relief-hillshade") return;
    if(productPrefs.dataLayers[layer.id]&&DUE_DILIGENCE_ENDPOINTS[layer.source]) sources.add(layer.source);
  });
  return sources;
}
function mapBboxParam(){
  if(!map) return "";
  const b=map.getBounds();
  return [b.getWest(),b.getSouth(),b.getEast(),b.getNorth()].map(v=>Number(v.toFixed(5))).join(",");
}
function dataUrlForSource(source){
  const base=DUE_DILIGENCE_ENDPOINTS[source];
  if(!base) return "";
  const bbox=mapBboxParam();
  const params=new URLSearchParams();
  if(bbox) params.set("bbox",bbox);
  if(source==="marketplace_listings"){
    Object.entries(productPrefs.marketplace||{}).forEach(([k,v])=>{
      if(!v||["view","sort"].includes(k)) return;
      params.set(k,String(v));
    });
  }
  const qs=params.toString();
  return qs?`${base}${base.includes("?")?"&":"?"}${qs}`:base;
}
function geojsonCentroid(g){
  if(!g) return null;
  if(g.type==="Point") return g.coordinates;
  const flat=[];
  (function walk(v){
    if(Array.isArray(v)&&v.length>=2&&Number.isFinite(Number(v[0]))&&Number.isFinite(Number(v[1]))) flat.push([Number(v[0]),Number(v[1])]);
    else if(Array.isArray(v)) v.forEach(walk);
  })(g.coordinates||[]);
  return flat.length?[flat.reduce((s,p)=>s+p[0],0)/flat.length,flat.reduce((s,p)=>s+p[1],0)/flat.length]:null;
}
function marketplacePointFeatures(features){
  return {type:"FeatureCollection",features:features.map(f=>{
    const c=geojsonCentroid(f.geometry);
    return c?{type:"Feature",id:f.id,geometry:{type:"Point",coordinates:c},properties:f.properties}:null;
  }).filter(Boolean)};
}
function selectedEntityFilters(){
  const f=productPrefs.assetGraph||{};
  return {rel:f.relationship_type||"",asset:f.asset_type||"",confidence:Number(f.confidence_min||0)};
}
function filterEntityAssetFeatures(features){
  const f=selectedEntityFilters();
  return (features||[]).filter(feature=>{
    const p=feature.properties||{},rel=p.asset_relationship||{};
    if(typeof rel==="string"){ try{ p.asset_relationship=JSON.parse(rel); }catch(_err){} }
    const r=p.asset_relationship||rel||{};
    if(f.rel&&r.relationship_type!==f.rel) return false;
    if(f.asset&&p.asset_type!==f.asset) return false;
    if(Number(r.confidence??p.confidence??0)<f.confidence) return false;
    return true;
  });
}
function selectedEntityLinkFeatures(entityId,features){
  const c=byId[entityId],loc=companyLoc(c);
  if(!loc) return [];
  const start=[loc.lon,loc.lat];
  return features.map(feature=>{
    const end=geojsonCentroid(feature.geometry),p=feature.properties||{},rel=p.asset_relationship||{};
    if(!end) return null;
    return {type:"Feature",id:`${entityId}:${p.id}:${rel.relationship_type||"ASSET"}`,geometry:{type:"LineString",coordinates:[start,end]},properties:{...rel,asset_id:p.id,asset_type:p.asset_type,name:p.name}};
  }).filter(Boolean);
}
async function loadCompanyAssetOverlay(entityId){
  if(!mapReady||!entityId) return;
  try{
    const res=await fetch(`/api/entity/${encodeURIComponent(entityId)}/asset-map.geojson`,{cache:"no-store"});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data=await res.json();
    assignSelectedEntityAssetFeatures(data.features||[]);
    const features=filterEntityAssetFeatures(selectedEntityAssetFeatures);
    map.getSource("selected_entity_assets")?.setData({type:"FeatureCollection",features});
    map.getSource("selected_entity_asset_links")?.setData({type:"FeatureCollection",features:selectedEntityLinkFeatures(entityId,features)});
  }catch(err){
    console.warn("entity asset overlay",err);
    assignSelectedEntityAssetFeatures([]);
    map.getSource("selected_entity_assets")?.setData(EMPTY_GEOJSON);
    map.getSource("selected_entity_asset_links")?.setData(EMPTY_GEOJSON);
  }
}
function refreshSelectedEntityAssetOverlay(){
  if(selected&&byId[selected]) loadCompanyAssetOverlay(selected);
}
function clearSourceCounts(source){
  Object.values(DATA_LAYER_BY_ID).forEach(layer=>{ if(layer.source===source) dataLayerCounts[layer.id]=0; });
}
async function loadDueDiligenceSource(source){
  if(!mapReady||!map?.getSource(source)||!DUE_DILIGENCE_ENDPOINTS[source]) return;
  dataSourceStatus[source]={state:"loading",count:dataSourceStatus[source]?.count||0,error:""};
  renderDataLayerPresets();
  try{
    const res=await fetch(dataUrlForSource(source),{cache:"no-store"});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data=await res.json();
    const features=Array.isArray(data.features)?data.features:[];
    map.getSource(source).setData({type:"FeatureCollection",features});
    if(source==="marketplace_listings"){
      assignMarketplaceListings(features.map(f=>f.properties||{}));
      map.getSource("marketplace_listing_points")?.setData(marketplacePointFeatures(features));
      renderMarketplaceResults();
    }
    clearSourceCounts(source);
    features.forEach(f=>{ const id=f?.properties?.layer; if(id) dataLayerCounts[id]=(dataLayerCounts[id]||0)+1; });
    dataSourceStatus[source]={state:features.length?"ready":"empty",count:features.length,error:""};
  }catch(err){
    console.warn("map intelligence source",source,err);
    map.getSource(source).setData(EMPTY_GEOJSON);
    if(source==="marketplace_listings"){
      assignMarketplaceListings([]);
      map.getSource("marketplace_listing_points")?.setData(EMPTY_GEOJSON);
      renderMarketplaceResults();
    }
    clearSourceCounts(source);
    dataSourceStatus[source]={state:"error",count:0,error:String(err?.message||err)};
  }
  renderDataLayerPresets();
}
function updateDueDiligenceSources(){
  if(!mapReady) return;
  clearTimeout(dueDiligenceLoadTimer);
  assignDueDiligenceLoadTimer(setTimeout(()=>{
    activeDataSources().forEach(source=>loadDueDiligenceSource(source));
  },120));
}
function layerFilter(layer){
  return ["==",["get","layer"],layer.id];
}
function iconName(icon){ return `dd-icon-${icon}`; }
function registerDueDiligenceIcon(name,color){
  const imageName=iconName(name);
  if(!map||map.hasImage?.(imageName)) return;
  const canvas=document.createElement("canvas"),size=30;
  canvas.width=size; canvas.height=size;
  const c=canvas.getContext("2d");
  c.clearRect(0,0,size,size);
  c.lineWidth=2.4; c.lineCap="round"; c.lineJoin="round";
  c.strokeStyle=color; c.fillStyle=color;
  c.shadowColor="rgba(0,0,0,.45)"; c.shadowBlur=2;
  const sx=size/24,px=x=>x*sx,py=y=>y*sx;
  function path(points,close=false,fill=false){
    c.beginPath();
    points.forEach(([x,y],i)=>i?c.lineTo(px(x),py(y)):c.moveTo(px(x),py(y)));
    if(close) c.closePath();
    fill?c.fill():c.stroke();
  }
  function rect(x,y,w,h){ c.strokeRect(px(x),py(y),px(w),py(h)); }
  function circle(x,y,r,fill=false){ c.beginPath(); c.arc(px(x),py(y),px(r),0,Math.PI*2); fill?c.fill():c.stroke(); }
  if(name==="factory"){ path([[3,20],[21,20]]); path([[5,20],[5,9],[10,12],[10,9],[15,12],[15,7],[19,7],[19,20]]); [[8,16],[12,16],[16,16]].forEach(p=>circle(p[0],p[1],.35,true)); }
  else if(name==="server"){ rect(5,4,14,6); rect(5,14,14,6); circle(8,7,.45,true); circle(8,17,.45,true); path([[12,7],[16,7]]); path([[12,17],[16,17]]); }
  else if(name==="hydro"){ circle(12,8,4); path([[12,4],[12,12]]); path([[8.5,10],[15.5,6]]); path([[4,16],[8,14.5],[12,16],[16,14.5],[20,16]]); path([[5,20],[9,18.5],[13,20],[17,18.5],[21,20]]); }
  else if(name==="energy"){ path([[13,2],[5,14],[12,14],[11,22],[19,9],[12,9]],true); }
  else if(name==="farm"){ path([[4,20],[9,15],[14,13],[20,13]]); path([[4,16],[9,14],[14,13],[20,13]]); path([[8,13],[8,8],[12,5],[16,4],[16,8],[13,11],[8,13]],true); }
  else if(name==="government"){ path([[3,21],[21,21]]); path([[5,9],[19,9]]); [6,10,14,18].forEach(x=>path([[x,18],[x,9]])); path([[12,3],[4,7],[20,7],[12,3]],true); }
  else if(name==="terrain"){ path([[3,20],[9,8],[13,15],[16,10],[21,20]],true); path([[9,8],[10.7,11],[13.7,11]]); }
  else if(name==="camera"){ rect(4,8,16,11); path([[8,8],[10,5],[14,5],[16,8]]); circle(12,13,3.2); }
  else if(name==="weather"){ path([[7,18],[17,18]]); c.beginPath(); c.arc(px(7),py(14.5),px(3.2),Math.PI*.55,Math.PI*1.75); c.arc(px(13),py(12),px(5),Math.PI,Math.PI*1.95); c.arc(px(17),py(14),px(4),Math.PI*1.25,Math.PI*.55); c.stroke(); }
  else if(name==="transmission"){ path([[12,3],[5,21]]); path([[12,3],[19,21]]); path([[8,12],[16,12]]); path([[6.5,17],[17.5,17]]); path([[7,7],[17,7]]); }
  else if(name==="river"){ path([[4,5],[9,6],[14,9],[20,7]]); path([[4,12],[9,13],[14,16],[20,14]]); path([[4,19],[8,18],[12,17]]); }
  else if(name==="barn"){ path([[4,21],[4,9],[12,4],[20,9],[20,21]]); path([[8,21],[8,14],[16,14],[16,21]]); path([[8,10],[16,10]]); path([[12,4],[12,10]]); }
  else if(name==="soil"){ path([[4,8],[8,7],[12,7],[16,7],[20,8]]); path([[4,13],[8,12],[12,12],[16,12],[20,13]]); path([[4,18],[8,17],[12,17],[16,17],[20,18]]); }
  else if(name==="tag"){ path([[4,12],[4,5],[11,5],[20,14],[13,21],[4,12]],true); circle(8,8,1); }
  else if(name==="home"){ path([[3,11],[12,3],[21,11]]); path([[5,10],[5,21],[19,21],[19,10]]); path([[10,21],[10,15],[14,15],[14,21]]); }
  else if(name==="storefront"){ path([[4,10],[20,10],[19,5],[5,5],[4,10]],true); path([[5,10],[5,20],[19,20],[19,10]]); path([[8,20],[8,14],[16,14],[16,20]]); path([[4,10],[8,10],[12,10],[16,10],[20,10]]); }
  else if(name==="warehouse"){ path([[3,21],[3,8],[12,4],[21,8],[21,21]]); path([[7,21],[7,13],[17,13],[17,21]]); path([[7,13],[17,13]]); path([[9,17],[15,17]]); }
  else if(name==="flag"){ path([[5,22],[5,4]]); path([[5,4],[17,4],[15,8],[17,12],[5,12]],true); path([[9,22],[15,22]]); }
  else if(name==="permit"){ path([[7,3],[14,3],[18,7],[18,21],[7,21],[7,3]],true); path([[14,3],[14,7],[18,7]]); path([[9,12],[15,12]]); path([[9,16],[14,16]]); }
  else if(name==="value"){ path([[12,2],[12,22]]); c.beginPath(); c.moveTo(px(17),py(6.5)); c.bezierCurveTo(px(15.8),py(5.2),px(9),py(4.6),px(9),py(8)); c.bezierCurveTo(px(9),py(12),px(18),py(10),px(18),py(15)); c.bezierCurveTo(px(18),py(18.6),px(10.8),py(18.8),px(9),py(15.8)); c.stroke(); }
  else if(name==="link"){ c.beginPath(); c.arc(px(8.5),py(12),px(4),Math.PI*.25,Math.PI*1.55); c.stroke(); c.beginPath(); c.arc(px(15.5),py(12),px(4),Math.PI*1.25,Math.PI*.55); c.stroke(); path([[9.5,12],[14.5,12]]); }
  else { path([[12,3],[3,20],[21,20],[12,3]],true); path([[12,9],[12,14]]); circle(12,17,.45,true); }
  const imgData=c.getImageData(0,0,size,size);
  map.addImage(imageName,imgData,{pixelRatio:2});
}
function registerDueDiligenceIcons(){
  Object.values(DATA_LAYER_BY_ID).forEach(layer=>registerDueDiligenceIcon(layer.icon,layer.color));
}
function addDueDiligenceSources(){
  DUE_DILIGENCE_SOURCES.forEach(id=>{
    if(!map.getSource(id)) map.addSource(id,{type:"geojson",data:EMPTY_GEOJSON,promoteId:"id"});
  });
  if(!map.getSource("marketplace_listing_points")) map.addSource("marketplace_listing_points",{type:"geojson",data:EMPTY_GEOJSON,promoteId:"id",cluster:true,clusterRadius:46,clusterMaxZoom:7});
  if(!map.getSource("selected_entity_assets")) map.addSource("selected_entity_assets",{type:"geojson",data:EMPTY_GEOJSON,promoteId:"id"});
  if(!map.getSource("selected_entity_asset_links")) map.addSource("selected_entity_asset_links",{type:"geojson",data:EMPTY_GEOJSON,promoteId:"id"});
}
function addDueDiligenceLayer(layer){
  const id=`dd-${layer.id}`;
  if(map.getLayer(id)||layer.layerType==="external") return;
  const base={id,source:layer.source,filter:layerFilter(layer),layout:{visibility:productPrefs.dataLayers[layer.id]?"visible":"none"}};
  if(layer.layerType==="line"){
    map.addLayer({...base,type:"line",layout:{...base.layout,"line-join":"round","line-cap":"round"},paint:{"line-color":layer.color,"line-width":2.1,"line-opacity":0.78,"line-dasharray":[1.4,1]}});
  }else if(layer.layerType==="fill"){
    map.addLayer({...base,type:"fill",paint:{"fill-color":layer.color,"fill-opacity":0.18,"fill-outline-color":layer.color}});
    if(layer.source==="marketplace_listings"&&!map.getLayer(`${id}-icon`)){
      map.addLayer({id:`${id}-icon`,type:"symbol",source:"marketplace_listing_points",filter:layerFilter(layer),layout:{visibility:productPrefs.dataLayers[layer.id]?"visible":"none","icon-image":iconName(layer.icon),"icon-size":0.78,"icon-allow-overlap":true,"icon-ignore-placement":true,"text-field":["coalesce",["get","title"],["get","name"],""],"text-size":10,"text-offset":[0,1.15],"text-anchor":"top","text-font":["Noto Sans Regular"]},paint:{"text-color":"#e5e7eb","text-halo-color":"#020617","text-halo-width":1.2}});
    }
  }else{
    map.addLayer({...base,type:"symbol",layout:{...base.layout,"icon-image":iconName(layer.icon),"icon-size":0.78,"icon-allow-overlap":true,"icon-ignore-placement":true,"text-field":["coalesce",["get","name"],""],"text-size":10,"text-offset":[0,1.15],"text-anchor":"top","text-font":["Noto Sans Regular"]},paint:{"text-color":"#e5e7eb","text-halo-color":"#020617","text-halo-width":1.2}});
  }
}
function addDueDiligenceLayers(){
  addDueDiligenceSources();
  registerDueDiligenceIcons();
  DATA_LAYER_PRESETS.flatMap(p=>p.layers).forEach(addDueDiligenceLayer);
  if(!map.getLayer("farm-hover-boundary")){
    map.addLayer({id:"farm-hover-boundary",type:"line",source:"farm_parcels",filter:["==",["get","id"],""],layout:{"line-join":"round","line-cap":"round","visibility":"visible"},paint:{"line-color":"#f8fafc","line-width":4,"line-opacity":0.95}});
  }
  if(!map.getLayer("marketplace-clusters")){
    map.addLayer({id:"marketplace-clusters",type:"circle",source:"marketplace_listing_points",filter:["has","point_count"],layout:{visibility:"none"},paint:{"circle-color":"#f59e0b","circle-radius":["step",["get","point_count"],15,5,22,20,31],"circle-opacity":0.78,"circle-stroke-color":"#fff","circle-stroke-width":1.4}});
    map.addLayer({id:"marketplace-cluster-count",type:"symbol",source:"marketplace_listing_points",filter:["has","point_count"],layout:{visibility:"none","text-field":["get","point_count_abbreviated"],"text-size":11,"text-font":["Noto Sans Bold"]},paint:{"text-color":"#fff"}});
  }
  addSelectedEntityAssetLayers();
  applyDueDiligenceLayerVisibility();
}
function relationshipLinkLayer(id,rels,color,dash){
  if(map.getLayer(id)) return;
  map.addLayer({id,type:"line",source:"selected_entity_asset_links",filter:["in",["get","relationship_type"],["literal",rels]],layout:{"line-join":"round","line-cap":"round","visibility":"visible"},paint:{"line-color":color,"line-width":2.2,"line-opacity":0.82,"line-dasharray":dash}});
}
function addSelectedEntityAssetLayers(){
  relationshipLinkLayer("entity-asset-link-ownership",["OWNS"],"#60a5fa",[1,0]);
  relationshipLinkLayer("entity-asset-link-operation",["OPERATES","MANAGES"],"#22c55e",[1,0]);
  relationshipLinkLayer("entity-asset-link-lease",["LEASES"],"#a78bfa",[1.6,1.2]);
  relationshipLinkLayer("entity-asset-link-finance",["FINANCES","LISTED_AS"],"#fbbf24",[1,0]);
  relationshipLinkLayer("entity-asset-link-permit",["PERMITS"],"#38bdf8",[.4,1.2]);
  relationshipLinkLayer("entity-asset-link-regulation",["REGULATES","LOCATED_ON","NEAR"],"#94a3b8",[.4,1.2]);
  relationshipLinkLayer("entity-asset-link-supply",["SUPPLIES","BUILDS","CONNECTED_TO"],"#f97316",[1.2,.8]);
  if(!map.getLayer("selected-entity-asset-fill")){
    map.addLayer({id:"selected-entity-asset-fill",type:"fill",source:"selected_entity_assets",filter:["in",["geometry-type"],["literal",["Polygon","MultiPolygon"]]],paint:{"fill-color":"#f59e0b","fill-opacity":0.16,"fill-outline-color":"#fbbf24"}});
  }
  if(!map.getLayer("selected-entity-assets")){
    map.addLayer({id:"selected-entity-assets",type:"symbol",source:"selected_entity_assets",layout:{"icon-image":["match",["get","asset_type"],"farm",iconName("farm"),"agricultural_land",iconName("farm"),"data_center",iconName("server"),"data_center_site",iconName("server"),"factory",iconName("factory"),"industrial_complex",iconName("factory"),"industrial_parcel",iconName("warehouse"),"warehouse",iconName("warehouse"),"government_facility",iconName("government"),"house",iconName("home"),"commercial_property",iconName("storefront"),"franchise_location",iconName("flag"),iconName("tag")],"icon-size":0.9,"icon-allow-overlap":true,"icon-ignore-placement":true,"text-field":["coalesce",["get","name"],""],"text-size":10,"text-offset":[0,1.2],"text-anchor":"top","text-font":["Noto Sans Regular"],"visibility":"visible"},paint:{"text-color":"#fff7ed","text-halo-color":"#020617","text-halo-width":1.4}});
  }
}
function scaledRadius(expr){ return ["*", Number(productPrefs.engine.nodeScale)||1, expr]; }
function applyProductPrefs(){
  const accent=productPrefs.engine.accent||"#ff3045";
  document.documentElement.style.setProperty("--accent",accent);
  document.documentElement.style.setProperty("--accent-2",accent);
  document.documentElement.style.setProperty("--accent-soft",accentSoft(accent));
  if(!mapReady) return;
  setLayerVisibility("terrain-hillshade",!!productPrefs.engine.terrain&&!!productPrefs.dataLayers["relief-hillshade"]);
  const labels=productPrefs.engine.labels;
  setLayerVisibility("company-labels-major",labels!=="none");
  setLayerVisibility("company-labels-close",labels==="close"||labels==="all");
  setLayerVisibility("security-labels",labels==="all");
  setLayerPaint("company-nodes","circle-radius",scaledRadius(nodeRadius()));
  setLayerPaint("company-halo","circle-radius",scaledRadius(["interpolate",["linear"],["coalesce",["get","degree"],1],1,10,100,30,300,50]));
  setLayerPaint("security-nodes","circle-radius",scaledRadius(["interpolate",["linear"],["coalesce",["get","degree"],1],1,3,25,5,100,9]));
  setLayerPaint("relationship-lines","line-opacity",0.25*Number(productPrefs.engine.edgeOpacity||1));
  applyDueDiligenceLayerVisibility();
}
function toggleToolPanel(id){
  const el=document.getElementById(id);
  if(!el) return;
  const show=!el.classList.contains("show");
  document.querySelectorAll(".tool-panel").forEach(p=>p.classList.remove("show"));
  assignActiveRailPanel("");
  document.getElementById("workspacePanel").classList.remove("show");
  document.querySelectorAll("#rail button, #gearPanel button[data-rail]").forEach(b=>b.classList.remove("active"));
  renderWorkspacePanel();
  if(show) el.classList.add("show");
}
window.addEventListener("beforeunload",saveViewNow);
syncThemeButton();
buildToolKinds();
applyProductPrefs();

fetch("data/universe_core.json").then(r=>r.json()).then(init).catch(()=>{ document.getElementById("loading").textContent="Could not load data/universe_core.json — run expand_us.py and serve this folder."; });
fetch("data/news.json").then(r=>r.ok?r.json():null).then(d=>{ if(d){ assignNEWS(d); updateFresh(); if(selected) select(selected); } }).catch(()=>{});
fetch("data/edge_candidates.json").then(r=>r.ok?r.json():[]).then(d=>{ assignEDGE_CANDIDATES(d||[]); if(selected) select(selected); }).catch(()=>{});
fetch("data/aliases.json").then(r=>r.ok?r.json():{}).then(d=>{ assignALIASES(d||{}); }).catch(()=>{});
fetch("data/hq_coords.json").then(r=>r.ok?r.json():{}).then(d=>{ Object.assign(HQ_CITY_COORDS,d||{}); COMPANIES.forEach(c=>delete c._loc); updateDataHealth(); if(mode==="globe") drawGlobe(); }).catch(()=>{});

function initNode(c){
  c.kind=c.kind||(c.private?"private":"public");
  c.group=c.group||c.sub||c.sector||"Other";
  c.grp=c.grp||c.group.toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/^_|_$/g,"");
  GROUPS[c.grp]=GROUPS[c.grp]||{name:c.group,color:SECTORS[c.sec]?.color||"#6b7682"};
  byId[c.id]=c; byId[c.canonical_id||c.id]=c; adj[c.id]=adj[c.id]||new Set(); c.ix=c.x; c.iy=c.y; c.tot=Number(c.tot||0);
}
function rebuildSelfView(){
  if(!selfViewId) return;
  const c=byId[selfViewId]||byId[ALIASES[selfViewId]];
  if(c) assignSelfViewId(c.id);
  assignSelfViewNodes(new Set(selfViewId?[selfViewId]:[]));
  LINKS.forEach(l=>{ if(l.from===selfViewId) selfViewNodes.add(l.to); if(l.to===selfViewId) selfViewNodes.add(l.from); });
}
function loadBulk(){
  if(bulkLoaded) return Promise.resolve();
  if(!bulkPromise){
    document.body.dataset.bulkFetches=String(Number(document.body.dataset.bulkFetches||0)+1);
    assignBulkPromise(fetch("data/universe_bulk.json")
    .then(r=>r.ok?r.json():{nodes:[]})
    .then(d=>{
      (d.nodes||[]).forEach(c=>{ initNode(c); c.r=5; COMPANIES.push(c); });
      assignBulkLoaded(true); rebuildSelfView(); buildGrid(); invalidateVisibilityCache();
    })
    .catch(err=>{ console.warn("bulk load skipped",err); assignBulkLoaded(true); }));
  }
  return bulkPromise;
}

function init(data){
  assignSECTORS(data.sectors); assignGROUPS(data.groups||{}); assignRELS(data.rels); assignCOMPANIES(data.nodes); assignLINKS(data.links);
  assignMETA(data.meta||{}); updateFresh();
  RELS.supplies.dir="supplier → customer"; RELS.funds.dir="investor → company"; RELS.partners.dir="mutual"; RELS.owns.dir="owner → subsidiary";
  if(RELS.contracts) RELS.contracts.dir="agency → contractor";
  if(RELS.acquired) RELS.acquired.dir="acquirer → legacy";
  if(RELS.government_action) RELS.government_action.dir="authority → entity";
  asOfInput.value=Math.min(Number(restoredView.asOf)||CURRENT_YEAR,CURRENT_YEAR);
  COMPANIES.forEach(initNode);
  LINKS.forEach(l=>{
    l.val=Number(l.val||0);
    if(!byId[l.from]||!byId[l.to]) return;
    adj[l.from].add(l.to); adj[l.to].add(l.from);
    byId[l.from].tot+=l.val; byId[l.to].tot+=l.val; assignMaxEdgeVal(Math.max(maxEdgeVal,l.val));
  });
  COMPANIES.forEach(c=>{ assignMaxNodeVal(Math.max(maxNodeVal,c.tot)); });
  COMPANIES.forEach(c=>{ c.r=c.deg?9+15*Math.sqrt(c.tot)/Math.sqrt(maxNodeVal):5; });
  buildGrid();
  Object.keys(SECTORS).forEach(k=>sectorOn[k]=true);
  Object.keys(GROUPS).forEach(k=>groupOn[k]=true);
  Object.keys(RELS).forEach(k=>relOn[k]=true);
  [...new Set(COMPANIES.map(c=>c.kind))].forEach(k=>kindOn[k]=true);
  applySavedFilters();

  assignEdgeEls(LINKS.map((l,i)=>{
    const p=document.createElementNS(SVGNS,"path"); p.setAttribute("class","edge"); p.dataset.i=i;
    p.addEventListener("pointerover",e=>{ setHoverNode(null); setHoverEdge(i); showEdgeTip(l,e.clientX,e.clientY); draw(); });
    p.addEventListener("pointermove",e=>showEdgeTip(l,e.clientX,e.clientY));
    p.addEventListener("pointerout",()=>{ setHoverEdge(null); hideTip(); draw(); });
    p.addEventListener("click",e=>{ e.stopPropagation(); openRelationshipEvidence(l); });
    gEdges.appendChild(p);
    const t=document.createElementNS(SVGNS,"text"); t.setAttribute("class","edge-label"); t.setAttribute("text-anchor","middle"); gLabels.appendChild(t);
    labelEls.push(t); return p;
  }));
  ensureNetworkNodes();
  console.assert(document.querySelectorAll("#nodes .node-g").length===COMPANIES.filter(c=>c.deg>0).length,"network node count mismatch");

  rebuildSelfView(); buildFilters(); buildToolKinds();
  (async()=>{
    if(selfViewId) await loadBulk();
    rebuildSelfView();
    const initialMode=savedMode();
    await setMode(initialMode);
    if(initialMode!=="globe") restoreSvgView();
    const restoreId=selfViewId||restoredView.selected;
    if(restoreId&&byId[restoreId]&&existsInYear(byId[restoreId])) select(restoreId);
    if(restoredView.manualSelectedId) showManualObject(restoredView.manualSelectedId);
    if(restoredView.modelerId&&byId[restoredView.modelerId]) openModeler(restoredView.modelerId);
    document.getElementById("loading").style.display="none";
    syncModeButton();
    assignRestoringView(false);
    saveViewNow();
    if(params.has("reliefDemo")) setTimeout(()=>zoomToTerrainDem(),350);
    if(params.has("stress")) setTimeout(()=>window.stressIndex(50000),0);
  })();
}

function nodeStroke(c){
  if(c.kind==="government") return "#58c7f3";
  if(c.kind==="security") return "#f0b341";
  if(c.kind==="private"||c.kind==="legacy") return "var(--text)";
  return "var(--bg)";
}
function nodeStrokeWidth(c){ return c.kind==="government"?2.2:(c.kind==="security"?2.1:(c.kind==="private"||c.kind==="legacy"?2:1.5)); }
function nodeLabelText(c){
  const raw=c.kind==="security"&&c.t?`${c.t} · ${(c.security_type||"SEC").toUpperCase()}`:c.n;
  return raw.length>20?raw.slice(0,18)+"…":raw;
}
function buildNode(c){
  if(nodeElsById[c.id]) return nodeElsById[c.id];
  const g=document.createElementNS(SVGNS,"g"); g.setAttribute("class","node-g"); g.dataset.id=c.id;
  const circ=document.createElementNS(SVGNS,"circle"); circ.setAttribute("class","node-circ"); circ.setAttribute("r",c.r);
  circ.setAttribute("fill",SECTORS[c.sec].color);
  circ.setAttribute("stroke",nodeStroke(c));
  circ.setAttribute("stroke-width",nodeStrokeWidth(c));
  if(c.kind==="security") circ.setAttribute("stroke-dasharray","5 3");
  else if(c.kind==="private"||c.kind==="legacy") circ.setAttribute("stroke-dasharray","3 2.5");
  g.appendChild(circ);
  let label=null;
  if(c.deg>0){ label=document.createElementNS(SVGNS,"text"); label.setAttribute("class","node-label"); label.setAttribute("text-anchor","middle"); label.setAttribute("y",c.r+13); label.textContent=nodeLabelText(c); g.appendChild(label); }
  gNodes.appendChild(g);
  const out={g,circ,label,c};
  nodeElsById[c.id]=out; nodeEls.push(out);
  return out;
}
function ensureNetworkNodes(){ COMPANIES.filter(c=>c.deg>0||(selfViewId&&selfViewNodes.has(c.id))).forEach(buildNode); }
function buildGrid(){
  assignGrid(new Map());
  COMPANIES.forEach(c=>{
    const gx=Math.floor(c.ix/90),gy=Math.floor(c.iy/90),key=gx+","+gy;
    if(!grid.has(key)) grid.set(key,[]);
    grid.get(key).push(c);
  });
}
function canvasHit(sx,sy){
  const p=screenToGraph(sx,sy),gx=Math.floor(p.x/90),gy=Math.floor(p.y/90);
  let best=null,bestD=Infinity,reach=Math.max(1,Math.ceil(20/k/90));
  for(let x=gx-reach;x<=gx+reach;x++) for(let y=gy-reach;y<=gy+reach;y++) (grid.get(x+","+y)||[]).forEach(c=>{
    if(!baseVisibleNode(c)) return;
    const d=(c.x-p.x)**2+(c.y-p.y)**2,limit=Math.max(c.r+4,14/k);
    if(d<limit*limit&&d<bestD){ best=c; bestD=d; }
  });
  return best;
}
function resizeCanvas(){
  const r=svg.getBoundingClientRect(),dpr=window.devicePixelRatio||1,w=Math.max(1,Math.floor(r.width*dpr)),h=Math.max(1,Math.floor(r.height*dpr));
  if(canvas.width!==w||canvas.height!==h){ canvas.width=w; canvas.height=h; canvas.style.width=r.width+"px"; canvas.style.height=r.height+"px"; }
  ctx.setTransform(dpr,0,0,dpr,0,0);
  return r;
}
function drawCanvas(){
  const r=resizeCanvas();
  ctx.clearRect(0,0,r.width,r.height);
  const minX=-tx/k-30,maxX=(r.width-tx)/k+30,minY=-ty/k-30,maxY=(r.height-ty)/k+30;
  visibleEdges().forEach(l=>{
    const a=byId[l.from],b=byId[l.to],g=edgeGeom(a,b);
    ctx.beginPath(); ctx.moveTo(g.sx*k+tx,g.sy*k+ty); ctx.quadraticCurveTo(g.mx*k+tx,g.my*k+ty,g.ex*k+tx,g.ey*k+ty);
    ctx.strokeStyle=RELS[l.rel].color; ctx.globalAlpha=selected&&l.from!==selected&&l.to!==selected ? .08 : .35; ctx.lineWidth=wWidth(l.val); ctx.stroke();
  });
  ctx.globalAlpha=1;
  COMPANIES.forEach(c=>{
    if(!visibleNode(c)||c.x<minX||c.x>maxX||c.y<minY||c.y>maxY) return;
    const x=c.x*k+tx,y=c.y*k+ty,r=Math.max(2,c.r*k);
    let op=1; if(selected) op=(c.id===selected||adj[selected]?.has(c.id))?1:.18;
    ctx.globalAlpha=op; ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2);
    ctx.fillStyle=SECTORS[c.sec]?.color||"#6b7682"; ctx.fill();
    if(c.id===selected){ ctx.lineWidth=2; ctx.strokeStyle="#e8edf4"; ctx.stroke(); }
  });
  ctx.globalAlpha=1;
}
function existsInYear(c){
  const y=activeYear(),born=yearOf(c.f),ended=yearOf(c.end_date);
  return (!born||born<=y)&&(!ended||ended>=y);
}
function activeEdge(l){
  if(!relOn[l.rel]) return false;
  const y=activeYear(),start=yearOf(l.start),end=yearOf(l.end),asOf=yearOf(l.as_of);
  if(start&&end) return start<=y&&y<=end;
  if(start) return start===y;
  if(asOf) return asOf===y;
  return true;
}
function baseVisibleNode(c){ return !!c && (!selfViewId||selfViewNodes.has(c.id)) && (!networkScope||mode!=="network"||networkScope.has(c.id)) && sectorOn[c.sec] && groupOn[c.grp] && kindOn[c.kind] && existsInYear(c); }
function invalidateVisibilityCache(){ assignVisibleEdgeCache(null); assignVisibleEdgeSet(null); assignLinkedNodeCache(null); }
function visibleEdgeRaw(l){ return activeEdge(l) && (!selfViewId||l.from===selfViewId||l.to===selfViewId) && baseVisibleNode(byId[l.from]) && baseVisibleNode(byId[l.to]); }
function rebuildVisibilityCache(){
  assignVisibleEdgeCache(LINKS.filter(visibleEdgeRaw));
  assignVisibleEdgeSet(new Set(visibleEdgeCache));
  assignLinkedNodeCache(new Set());
  visibleEdgeCache.forEach(l=>{ linkedNodeCache.add(l.from); linkedNodeCache.add(l.to); });
}
function visibleEdges(){ if(!visibleEdgeCache) rebuildVisibilityCache(); return visibleEdgeCache; }
function hasVisibleEdge(c){ if(!linkedNodeCache) rebuildVisibilityCache(); return linkedNodeCache.has(c.id); }
function networkLinkedNode(c){ return baseVisibleNode(c)&&hasVisibleEdge(c); }
function visibleNode(c){ if(!baseVisibleNode(c)) return false; if(c.id===selected||selfViewId) return true; if(mode==="network") return networkScope?networkScope.has(c.id):hasVisibleEdge(c); return true; }
function visibleEdge(l){ if(!visibleEdgeSet) rebuildVisibilityCache(); return visibleEdgeSet.has(l); }
function wWidth(v){ return v<=0?1.4:1.4+5.5*Math.sqrt(v)/Math.sqrt(maxEdgeVal); }
function nodeAnchored(c){ return !!c && (c.fixed||hoverFrozenIds.has(c.id)); }
function neighborhoodIds(id){
  if(!id||!byId[id]) return null;
  const ids=new Set([id]);
  (adj[id]||new Set()).forEach(otherId=>{ if(byId[otherId]&&baseVisibleNode(byId[otherId])) ids.add(otherId); });
  return ids;
}
function hoverNeighborhoodIds(){
  if(mode!=="network"||selected||!hoverNodeId) return null;
  return neighborhoodIds(hoverNodeId);
}
function syncHoverFreeze(){
  hoverFrozenIds.clear();
  if(hoverNodeId&&byId[hoverNodeId]) (neighborhoodIds(hoverNodeId)||new Set()).forEach(id=>hoverFrozenIds.add(id));
  if(hovEdge===null) return;
  const l=LINKS[hovEdge];
  if(!l) return;
  if(byId[l.from]) hoverFrozenIds.add(l.from);
  if(byId[l.to]) hoverFrozenIds.add(l.to);
}
function physicsPaused(){ return mode==="network" && (!productPrefs.engine.motion || (!dragNode && (hoverNodeId || hovEdge!==null))); }
function setHoverNode(id){
  const next=id&&byId[id]?id:null;
  if(hoverNodeId===next) return;
  assignHoverNodeId(next);
  syncHoverFreeze();
}
function setHoverEdge(i){
  const next=Number.isInteger(i)?i:null;
  if(hovEdge===next) return;
  assignHovEdge(next);
  syncHoverFreeze();
}
function clearHoverFreeze(){
  assignHoverNodeId(null);
  assignHovEdge(null);
  hoverFrozenIds.clear();
}
function queueHover(n,x,y){
  assignPendingHover({n,x,y});
  if(hoverFrame) return;
  assignHoverFrame(requestAnimationFrame(()=>{
    hoverFrame=0;
    const h=pendingHover; assignPendingHover(null);
    if(!h) return;
    setHoverNode(mode==="network"&&h.n?h.n.id:null);
    if(h.n) showNodeTip(h.n,h.x,h.y); else hideTip();
    draw();
  }));
}

const NODE_COLLISION_PAD=8;

// Keep circles from ever occupying the same space, even when one node is dragged.
function resolveNodeCollisions(nodes,focusNode=null,passes=1){
  if(!nodes.length) return;
  for(let pass=0;pass<passes;pass++){
    for(let i=0;i<nodes.length;i++){
      const a=nodes[i];
      for(let j=i+1;j<nodes.length;j++){
        const b=nodes[j];
        let dx=b.x-a.x,dy=b.y-a.y;
        if(!Number.isFinite(dx)||!Number.isFinite(dy)) continue;
        let d=Math.hypot(dx,dy);
        const minDist=a.r+b.r+NODE_COLLISION_PAD;
        if(d>=minDist) continue;
        if(!d){
          dx=(a.ix||a.x)-(b.ix||b.x);
          dy=(a.iy||a.y)-(b.iy||b.y);
          d=Math.hypot(dx,dy)||1;
        }
        const ux=dx/d,uy=dy/d,shift=minDist-d;
        const aLocked=nodeAnchored(a),bLocked=nodeAnchored(b);
        if(aLocked&&bLocked){
          if(focusNode===a&&!b.fixed&&!hoverFrozenIds.has(b.id)){ b.x+=ux*shift; b.y+=uy*shift; }
          else if(focusNode===b&&!a.fixed&&!hoverFrozenIds.has(a.id)){ a.x-=ux*shift; a.y-=uy*shift; }
          continue;
        }
        if(aLocked||focusNode===b){
          b.x+=ux*shift; b.y+=uy*shift;
          continue;
        }
        if(bLocked||focusNode===a){
          a.x-=ux*shift; a.y-=uy*shift;
          continue;
        }
        const half=shift/2;
        a.x-=ux*half; a.y-=uy*half;
        b.x+=ux*half; b.y+=uy*half;
      }
    }
  }
}

function edgeGeom(a,b){
  let dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,ux=dx/d,uy=dy/d;
  const sx=a.x+ux*(a.r+2),sy=a.y+uy*(a.r+2),ex=b.x-ux*(b.r+7),ey=b.y-uy*(b.r+7);
  const cv=d*0.13,mx=(sx+ex)/2-uy*cv,my=(sy+ey)/2+ux*cv;
  return {sx,sy,ex,ey,mx,my};
}

function draw(){
  if(mode==="globe"){ drawGlobe(); return; }
  if(mode==="index"){ drawCanvas(); return; }
  const hoverIds=hoverNeighborhoodIds();
  LINKS.forEach((l,i)=>{
    const p=edgeEls[i],t=labelEls[i],a=byId[l.from],b=byId[l.to];
    if(!visibleEdge(l)){ p.style.display="none"; t.style.display="none"; return; }
    p.style.display="";
    const g=edgeGeom(a,b);
    p.setAttribute("d",`M${g.sx} ${g.sy} Q ${g.mx} ${g.my} ${g.ex} ${g.ey}`);
    p.setAttribute("stroke",RELS[l.rel].color);
    p.setAttribute("stroke-width",wWidth(l.val));
    if(l.rel!=="partners"){ p.setAttribute("marker-end",`url(#arr-${l.rel})`); p.removeAttribute("stroke-dasharray"); }
    else { p.removeAttribute("marker-end"); p.setAttribute("stroke-dasharray","5 4"); }
    const incident=selected&&(l.from===selected||l.to===selected);
    const hoverIncident=hoverIds&&(l.from===hoverNodeId||l.to===hoverNodeId);
    let op=.55;
    if(selected) op=incident?1:.06;
    else if(hoverIds) op=hoverIncident?1:.04;
    if(hovEdge===i) op=1;
    p.style.opacity=op;
    if(((incident||hoverIncident||hovEdge===i)&&l.val>0)){ t.style.display=""; t.setAttribute("x",g.mx); t.setAttribute("y",g.my-3); t.textContent=fmtBn(l.val); t.style.opacity=op; }
    else t.style.display="none";
  });
  nodeEls.forEach(o=>{
    if(!visibleNode(o.c)){ o.g.style.display="none"; return; } o.g.style.display="";
    o.g.setAttribute("transform",`translate(${o.c.x},${o.c.y})`);
    let op=1;
    if(selected) op=(o.c.id===selected||adj[selected].has(o.c.id))?1:.08;
    else if(hoverIds) op=hoverIds.has(o.c.id)?1:.06;
    if(hovEdge!==null){ const l=LINKS[hovEdge]; op=(o.c.id===l.from||o.c.id===l.to)?1:.12; }
    o.g.style.opacity=op;
    o.circ.setAttribute("stroke",o.c.id===selected?"var(--text)":nodeStroke(o.c));
    o.circ.setAttribute("stroke-width",o.c.id===selected?2.8:nodeStrokeWidth(o.c));
    if(o.label){
      const showLabel=selected?(o.c.id===selected||adj[selected].has(o.c.id)):hoverIds?hoverIds.has(o.c.id):hovEdge!==null?((LINKS[hovEdge]?.from===o.c.id)||(LINKS[hovEdge]?.to===o.c.id)):true;
      o.label.style.display=showLabel?"":"none";
    }
  });
}

/* ---------- view ---------- */
let k=1,tx=0,ty=0;
let labelCollideTimer=0;
function queueLabelCollisions(){ clearTimeout(labelCollideTimer); labelCollideTimer=setTimeout(resolveLabelCollisions,140); }
// Grid-bucket sweep: after layout/zoom settles, hide labels that overlap a
// higher-degree label already placed. Cheapest effective de-crowding — no physics lib.
function resolveLabelCollisions(){
  if(mode!=="network") return; // debounced off zoom/pan; batched read/write keeps it cheap
  const nodes=COMPANIES.filter(c=>c.deg>0&&visibleNode(c)&&nodeElsById[c.id]).sort((a,b)=>(b.deg||0)-(a.deg||0));
  const labels=[];
  for(const c of nodes){ const l=nodeElsById[c.id].label; if(l){ l.classList.remove("collide-hidden"); labels.push(l); } }
  const rects=labels.map(l=>l.getBoundingClientRect()); // batch reads after batch writes — one reflow
  const cell=42, occupied=new Set(), toHide=[];
  for(let i=0;i<labels.length;i++){
    const r=rects[i]; if(!r.width) continue; // dim/off-screen labels aren't laid out
    const x0=Math.floor(r.left/cell),x1=Math.floor(r.right/cell),y0=Math.floor(r.top/cell),y1=Math.floor(r.bottom/cell);
    let clash=false;
    for(let x=x0;x<=x1&&!clash;x++) for(let y=y0;y<=y1;y++){ if(occupied.has(x+","+y)){ clash=true; break; } }
    if(clash) toHide.push(labels[i]);
    else for(let x=x0;x<=x1;x++) for(let y=y0;y<=y1;y++) occupied.add(x+","+y);
  }
  for(const l of toHide) l.classList.add("collide-hidden");
}
function applyView(){ vp.setAttribute("transform",`translate(${tx},${ty}) scale(${k})`); gNodes.classList.toggle("zoomed",k>1.4); if(mode==="index") drawCanvas(); if(mode==="network") queueLabelCollisions(); queueSaveView(); }
function bounds(){ let a=1e9,b=1e9,c=-1e9,d=-1e9,any=false; COMPANIES.forEach(n=>{ if(!visibleNode(n))return; any=true; a=Math.min(a,n.x);b=Math.min(b,n.y);c=Math.max(c,n.x);d=Math.max(d,n.y); }); return any?{minX:a,minY:b,maxX:c,maxY:d}:{minX:0,minY:0,maxX:1000,maxY:700}; }
function fit(){ const r=svg.getBoundingClientRect(),bb=bounds(),pad=mode==="network"?160:90,w=bb.maxX-bb.minX+pad*2,h=bb.maxY-bb.minY+pad*2; k=Math.min(r.width/w,r.height/h); tx=(r.width-w*k)/2-(bb.minX-pad)*k; ty=(r.height-h*k)/2-(bb.minY-pad)*k; applyView(); }
function screenToGraph(sx,sy){ const r=svg.getBoundingClientRect(); return {x:(sx-r.left-tx)/k,y:(sy-r.top-ty)/k}; }
svg.addEventListener("wheel",e=>{
  e.preventDefault();
  const r=svg.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top,f=e.deltaY<0?1.12:1/1.12,nk=Math.max(.08,Math.min(7,k*f));
  tx=mx-(nk/k)*(mx-tx); ty=my-(nk/k)*(my-ty); k=nk; applyView();
},{passive:false});

/* ---------- interaction ---------- */
let dragNode=null,downNode=null,panning=false,moved=false,last={x:0,y:0};
function nodeFrom(e){
  if(mode==="index") return canvasHit(e.clientX,e.clientY);
  let el=e.target;
  while(el&&el!==svg){ if(el.dataset&&el.dataset.id) return byId[el.dataset.id]; el=el.parentNode; }
  return null;
}
svg.addEventListener("pointerdown",e=>{
  if(e.target.classList&&e.target.classList.contains("edge")) return; const n=nodeFrom(e); moved=false; last={x:e.clientX,y:e.clientY}; if(n&&mode==="network"){ dragNode=n; dragNode.fixed=true; svg.setPointerCapture(e.pointerId);} else if(n){ downNode=n; svg.setPointerCapture(e.pointerId); } else { panning=true; svg.classList.add("panning"); }
});
svg.addEventListener("pointermove",e=>{
  if(dragNode){
    const p=screenToGraph(e.clientX,e.clientY);
    dragNode.x=p.x; dragNode.y=p.y;
    if(mode==="network") resolveNodeCollisions(COMPANIES.filter(visibleNode),dragNode,2);
    if(Math.abs(e.clientX-last.x)>3||Math.abs(e.clientY-last.y)>3) moved=true;
    draw();
  }
  else if(downNode){ if(Math.abs(e.clientX-last.x)>3||Math.abs(e.clientY-last.y)>3) moved=true; }
  else if(panning){ tx+=e.clientX-last.x; ty+=e.clientY-last.y; last={x:e.clientX,y:e.clientY}; applyView(); }
  else if(!e.target.classList.contains("edge")){
    const n=nodeFrom(e);
    queueHover(n,e.clientX,e.clientY);
  }
});
svg.addEventListener("pointerup",e=>{
  if(dragNode){ dragNode.fixed=false; if(!moved) select(dragNode.id); } else if(downNode&&!moved){ select(downNode.id); } else if(panning&&!moved&&!nodeFrom(e)) deselect(); dragNode=null; downNode=null; panning=false; svg.classList.remove("panning");
});
svg.addEventListener("pointerleave",()=>{ assignPendingHover(null); clearHoverFreeze(); hideTip(); draw(); });

function showNodeTip(n,x,y){
  const km=kindMeta[n.kind]||{name:n.kind,color:"var(--text-2)"};
  const links=visibleEdges()
    .filter(l=>l.from===n.id||l.to===n.id)
    .map(l=>({l,other:byId[l.from===n.id?l.to:l.from]}))
    .filter(x=>x.other)
    .sort((a,b)=>(b.l.val||0)-(a.l.val||0)||a.other.n.localeCompare(b.other.n));
  const shown=links.slice(0,HOVER_LINK_CAP);
  const more=links.length-shown.length;
  const preview=shown.length?`<div class="tip-list">${shown.map(({l,other})=>`<div class="tip-link">${esc(other.n)} · ${esc(RELS[l.rel]?.name||l.rel)}</div>`).join("")}</div>`:"";
  const moreText=more>0?`<div class="t3 tip-more">${shown.length} of ${links.length} connections shown · click for more connections</div>`:`<div class="t3">Click to pin and open the full panel</div>`;
  // Reuse drawer data access (no new fetches on hover): HQ · exchange · confidence + latest signal.
  const hq=hqSummary(n);
  const meta=[hq.text&&hq.text!=="—"?hq.text:"",n.exchange||"",`${confidenceBand(n.source_confidence)} confidence`].filter(Boolean).join(" · ");
  const f=latestFiling(n),news=(NEWS.items_by_node?.[n.id]||[])[0];
  const sig=f?.filingDate?`${f.form||f.type||"Filing"} · ${f.filingDate}`:(news?.date?`News · ${news.date}`:"");
  tip.innerHTML=`<b>${esc(n.n)}</b><span class="t2">${esc(entityTypeLabel(n))} · ${esc(n.group||SECTORS[n.sec]?.name||"")}</span>${meta?`<div class="t3">${esc(meta)}</div>`:""}${sig?`<div class="t3">Latest · ${esc(sig)}</div>`:""}${n.tot>0?`<div class="t3">${fmtBn(n.tot)} mapped value · ${n.deg} links</div>`:`<div class="t3">No mapped value yet</div>`}${preview}${moreText}`;
  place(x,y);
}
function showEdgeTip(l,x,y){
  const a=byId[l.from],b=byId[l.to],arrow=l.rel==="partners"?"↔":"→",dates=edgeDateText(l);
  tip.innerHTML=`<b>${esc(a.n)} ${arrow} ${esc(b.n)}</b><span class="t2">${esc(RELS[l.rel].name)} · ${esc(l.detail)}</span><div class="t3">source: ${esc(l.src||"curated")}${dates?` · ${esc(dates)}`:""}</div>`;
  place(x,y);
}
function openRelationshipEvidence(l){
  const a=byId[l.from]||{},b=byId[l.to]||{},edgeId=l.id||`${l.from}:${l.rel}:${l.to}`;
  detail.innerHTML=`<div class="hd"><div class="top"><div><h2>${esc(RELS[l.rel]?.name||l.rel||"Relationship")}</h2><div class="tick">${esc(a.n||l.from)} → ${esc(b.n||l.to)}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div>
    <span class="badge outline">${esc(l.rel||"edge")}</span><span class="badge signal">${confidencePct(l.confidence||l.conf||.7)} confidence</span>
    <div class="meta"><div><span>Source entity</span><b>${esc(a.n||l.from)}</b></div><div><span>Target</span><b>${esc(b.n||l.to)}</b></div><div><span>Value</span><b>${l.val?fmtBn(l.val):"—"}</b></div><div><span>Source</span><b>${esc(l.src||"curated")}</b></div><div><span>As of</span><b>${esc(edgeDateText(l)||l.as_of_date||"date pending")}</b></div><div><span>Status</span><b>${esc(l.status||"inferred")}</b></div></div></div>
    <div class="body">${evidenceBlock("relationship",edgeId)}<div class="story-meta">Network-edge provenance uses available source metadata. Asset bridge edges expose full evidence records when linked in the geospatial backend.</div></div>`;
  detail.classList.add("show");
  hydrateEvidence("relationship",edgeId);
}
function listValue(v){
  if(Array.isArray(v)) return v.filter(Boolean);
  if(typeof v==="string"&&v.trim().startsWith("[")){
    try{ const parsed=JSON.parse(v); if(Array.isArray(parsed)) return parsed.filter(Boolean); }catch(_err){}
  }
  return v?[String(v)]:[];
}
function compactMoney(v){
  const n=Number(v);
  return Number.isFinite(n)?`$${Math.round(n).toLocaleString()}`:"—";
}
function setFarmHover(id){
  if(hoveredFarmId===id) return;
  assignHoveredFarmId(id||"");
  if(map?.getLayer("farm-hover-boundary")) map.setFilter("farm-hover-boundary",hoveredFarmId?["==",["get","id"],hoveredFarmId]:["==",["get","id"],""]);
}
function showFarmTip(p,x,y){
  const crops=listValue(p.crop_history),activity=p.main_crop||crops[0]||"crop history pending";
  tip.innerHTML=`<b>${esc(p.name||"Farm parcel")}</b><span class="t2">${esc(p.farm_type||p.asset_type||"farm")} · ${esc(p.area_acres||p.acres||"—")} acres</span><div class="t3">${esc(activity)} · soil ${esc(p.soil_quality||"pending")} · risk ${esc(p.risk_level||p.risk_score||"pending")}</div>`;
  place(x,y);
}
function assetLocation(a){
  return [a.address,a.county,a.state,a.country].filter(Boolean).join(" · ")||"—";
}
function permitRows(permits){
  return permits?.length?permits.map(p=>`<div class="meta-row">${esc(p.permit_type||"permit")} · ${esc(p.approval_status||"status pending")} · ${compactMoney(p.estimated_cost)}</div>`).join(""):`<div class="meta-row">No public permit records loaded yet.</div>`;
}
function valuationBlock(assetId){
  return `<div class="farm-detail valuation-block" data-valuation-asset="${esc(assetId)}" data-case="base"><div class="section-h">Valuation</div><div class="story-meta">Loading deterministic valuation model…</div></div>`;
}
function assumptionInputs(v){
  const a=v.assumptions||{},keys=["revenue","cost","growth","discount_rate","utilization","yield","capex","tax_incentives","risk_adjustment"];
  return `<div class="assumption-grid">${keys.map(k=>`<label>${esc(k.replaceAll("_"," "))}<input type="number" step="any" data-assumption-key="${esc(k)}" value="${esc(a[k]??"")}"></label>`).join("")}</div>`;
}
function renderValuation(host,v){
  const missing=v.missing_data_fields||[],breakdown=v.score_breakdown||[];
  host.innerHTML=`<div class="section-h">Valuation</div>
    <div class="valuation-tools"><button type="button" data-action="valuation-case" data-case="bear" class="${v.case==="bear"?"active":""}">Bear</button><button type="button" data-action="valuation-case" data-case="base" class="${v.case==="base"?"active":""}">Base</button><button type="button" data-action="valuation-case" data-case="bull" class="${v.case==="bull"?"active":""}">Bull</button><button type="button" data-action="valuation-save">Save</button></div>
    <div class="kpis"><div class="kpi"><div class="v">${esc(v.headline_recommendation||"watch")}</div><div class="l">headline recommendation</div></div><div class="kpi"><div class="v">${esc(v.score??"—")}/100</div><div class="l">risk-adjusted score</div></div><div class="kpi"><div class="v">${confidencePct(v.confidence_score)}</div><div class="l">confidence</div></div></div>
    <div class="meta"><div><span>Estimated value</span><b>${compactMoney(v.estimated_current_value)}</b></div><div><span>Last sale</span><b>${compactMoney(v.last_known_sale_price)}</b></div><div><span>Listing / acquisition</span><b>${compactMoney(v.acquisition_price)}</b></div><div><span>Annual revenue</span><b>${compactMoney(v.estimated_annual_revenue)}</b></div><div><span>Annual cost</span><b>${compactMoney(v.estimated_annual_operating_cost)}</b></div><div><span>Yearly gain/loss</span><b>${compactMoney(v.estimated_yearly_gain_loss)}</b></div><div><span>Payback</span><b>${v.payback_period!=null?`${esc(v.payback_period)} yrs`:"—"}</b></div><div><span>NPV</span><b>${compactMoney(v.npv)}</b></div><div><span>Risk score</span><b>${esc(v.risk_score??"—")}</b></div></div>
    ${missing.length?`<div class="section-h">Missing Data</div><div class="story-meta">${esc(missing.join(" · "))}</div>`:""}
    <div class="section-h">Assumptions</div>${assumptionInputs(v)}
    <div class="section-h">Why This Score</div><div class="score-breakdown">${breakdown.map(x=>`<div class="score-row"><span>${esc(x.factor)}</span><b>${Number(x.points)>0?"+":""}${esc(x.points)}</b></div>`).join("")||`<div class="story-meta">No factor breakdown loaded.</div>`}</div>
    <div class="section-h">Sources</div><div class="story-meta">${esc((v.source_list||[]).join(" · ")||"source pending")} · ${esc(v.disclaimer||"Modeled estimate, not a guarantee.")}</div>`;
}
async function hydrateValuation(assetId,caseName="base"){
  const host=document.querySelector(`[data-valuation-asset="${CSS.escape(assetId)}"]`);
  if(!host) return;
  host.dataset.case=caseName;
  try{
    const res=await fetch(`/api/assets/${encodeURIComponent(assetId)}/valuation?case=${encodeURIComponent(caseName)}`,{cache:"no-store"});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    renderValuation(host,await res.json());
  }catch(err){
    host.innerHTML=`<div class="section-h">Valuation</div><div class="story-meta">Could not load valuation: ${esc(err.message||err)}</div>`;
  }
}
async function saveValuationAssumptions(host){
  const assetId=host?.dataset.valuationAsset,caseName=host?.dataset.case||"custom";
  if(!assetId) return;
  const assumptions={};
  host.querySelectorAll("[data-assumption-key]").forEach(input=>{ const n=Number(input.value); if(Number.isFinite(n)) assumptions[input.dataset.assumptionKey]=n; });
  const res=await fetch(`/api/assets/${encodeURIComponent(assetId)}/valuation-assumptions`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({case:caseName,assumptions})});
  if(res.ok) hydrateValuation(assetId,caseName);
}
function evidenceBlock(objectType,objectId){
  return `<div class="farm-detail evidence-block" data-evidence-object-type="${esc(objectType)}" data-evidence-object-id="${esc(objectId)}"><div class="section-h">Evidence</div><div class="story-meta">Loading source provenance…</div></div>`;
}
function evidenceTags(row){
  const tags=[];
  const status=String(row.status||"inferred").toLowerCase();
  tags.push(status==="confirmed"?"Confirmed":status==="estimated"?"Estimated":"Inferred");
  if(Number(row.confidence)<.6) tags.push("Low confidence");
  if(!row.source_name||row.source_name==="source pending") tags.push("Missing source");
  const d=row.source_date||row.retrieved_at;
  if(!d) tags.push("Stale"); else {
    const then=new Date(d),age=(Date.now()-then.getTime())/86400000;
    if(Number.isFinite(age)&&age>365) tags.push("Stale");
  }
  return `<div class="evidence-tags">${tags.map(t=>`<span class="evidence-tag ${/low|missing/i.test(t)?"bad":/stale|inferred|estimated/i.test(t)?"warn":""}">${esc(t)}</span>`).join("")}</div>`;
}
function claimValue(v){
  if(Array.isArray(v)) return v.join(" · ");
  if(v&&typeof v==="object") return JSON.stringify(v);
  return v??"—";
}
function renderEvidence(host,evidence,overrides){
  const objectType=host.dataset.evidenceObjectType,objectId=host.dataset.evidenceObjectId;
  const rows=evidence.slice(0,18).map(row=>{
    const link=row.source_url?` · <a href="${esc(row.source_url)}" target="_blank" rel="noopener noreferrer">public link</a>`:"";
    return `<div class="evidence-row"><b>${esc(row.claim_type)}: ${esc(claimValue(row.claim_value))}</b><span>${esc(row.source_name||"source pending")} · ${esc(row.source_date||row.retrieved_at||"date pending")} · confidence ${confidencePct(row.confidence)}${link}</span>${evidenceTags(row)}${row.notes?`<div class="story-meta">${esc(row.notes)}</div>`:""}</div>`;
  }).join("")||`<div class="story-meta">No provenance records loaded for this object yet.</div>`;
  const overrideRows=overrides.map(row=>`<div class="override-row"><b>${esc(row.field_name)}: ${esc(claimValue(row.old_value))} → ${esc(claimValue(row.new_value))}</b><span>User override · ${esc(row.review_status||"pending")} · ${esc(row.created_at||"")}</span>${row.user_note?`<div class="story-meta">${esc(row.user_note)}</div>`:""}<button type="button" data-action="delete-override" data-override-id="${esc(row.id)}">Revert override</button></div>`).join("");
  host.innerHTML=`<div class="section-h">Evidence</div>
    <div class="evidence-actions"><button class="primary" type="button" data-action="generate-report" data-object-type="${esc(objectType)}" data-object-id="${esc(objectId)}">Generate report</button><button type="button" data-action="add-override" data-object-type="${esc(objectType)}" data-object-id="${esc(objectId)}">Add correction</button></div>
    <div class="evidence-list">${rows}</div>
    <div class="section-h">Local Overrides</div><div class="override-list">${overrideRows||`<div class="story-meta">No local corrections saved. Original source values remain unchanged.</div>`}</div>
    <div class="story-meta" data-report-status></div>`;
}
async function hydrateEvidence(objectType,objectId){
  const host=document.querySelector(`[data-evidence-object-type="${CSS.escape(objectType)}"][data-evidence-object-id="${CSS.escape(objectId)}"]`);
  if(!host) return;
  try{
    const [evRes,ovRes]=await Promise.all([
      fetch(`/api/evidence?object_type=${encodeURIComponent(objectType)}&object_id=${encodeURIComponent(objectId)}`,{cache:"no-store"}),
      fetch(`/api/overrides?object_type=${encodeURIComponent(objectType)}&object_id=${encodeURIComponent(objectId)}`,{cache:"no-store"})
    ]);
    if(!evRes.ok) throw new Error(`${evRes.status} evidence`);
    renderEvidence(host,(await evRes.json()).evidence||[],ovRes.ok?((await ovRes.json()).overrides||[]):[]);
  }catch(err){
    host.innerHTML=`<div class="section-h">Evidence</div><div class="story-meta">Could not load provenance: ${esc(err.message||err)}</div>`;
  }
}
async function addOverride(objectType,objectId){
  const field=prompt("Field to correct, e.g. acreage, owner, listing_status");
  if(!field) return;
  const newValue=prompt(`New value for ${field}`);
  if(newValue===null) return;
  const userNote=prompt("Note/source for this correction")||"";
  await fetch("/api/overrides",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({object_type:objectType,object_id:objectId,field_name:field,new_value:newValue,user_note:userNote})});
  hydrateEvidence(objectType,objectId);
}
async function deleteOverride(id){
  await fetch(`/api/overrides/${encodeURIComponent(id)}`,{method:"DELETE"});
  document.querySelectorAll("[data-evidence-object-type][data-evidence-object-id]").forEach(host=>hydrateEvidence(host.dataset.evidenceObjectType,host.dataset.evidenceObjectId));
}
async function generateReport(objectType,objectId){
  const host=document.querySelector(`[data-evidence-object-type="${CSS.escape(objectType)}"][data-evidence-object-id="${CSS.escape(objectId)}"]`),status=host?.querySelector("[data-report-status]");
  if(status) status.textContent="Generating due-diligence report…";
  try{
    const res=await fetch(`/api/reports/${encodeURIComponent(objectType)}/${encodeURIComponent(objectId)}/generate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sections:["overview","permits","infrastructure","risk","valuation","evidence"]})});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const out=await res.json();
    if(status) status.innerHTML=`Report ready: <a href="${esc(out.html)}" target="_blank" rel="noopener noreferrer">HTML</a> · <a href="${esc(out.csv)}" target="_blank" rel="noopener noreferrer">CSV evidence</a> · <a href="${esc(out.json)}" target="_blank" rel="noopener noreferrer">JSON</a> · PDF ${esc(out.pdf||"placeholder")}`;
  }catch(err){
    if(status) status.textContent=`Report failed: ${err.message||err}`;
  }
}
function showIndustrialTip(p,x,y){
  tip.innerHTML=`<b>${esc(p.name||"Industrial asset")}</b><span class="t2">${esc(p.industrial_type||p.asset_type||"industrial")} · ${esc(p.owner_name||"owner pending")}</span><div class="t3">${esc(p.status||"status pending")} · project ${compactMoney(p.estimated_project_cost)} · ${esc(p.power_capacity_mw||"—")} MW · permits ${esc(p.permit_status||"not loaded")} · confidence ${confidencePct(p.confidence)}</div>`;
  place(x,y);
}
function showGovernmentTip(p,x,y){
  tip.innerHTML=`<b>${esc(p.name||"Government facility")}</b><span class="t2">${esc(p.agency_type||p.facility_type||"public facility")} · ${esc(p.jurisdiction||"jurisdiction pending")}</span><div class="t3">${esc(p.source||"public source")} · confidence ${confidencePct(p.confidence)}</div>`;
  place(x,y);
}
function showListingTip(p,x,y){
  const size=p.acreage?`${p.acreage} acres`:(p.square_feet?`${Number(p.square_feet).toLocaleString()} sq ft`:"size pending");
  tip.innerHTML=`<b>${esc(p.title||"Marketplace listing")}</b><span class="t2">${esc(p.asset_type||"asset")} · ${compactMoney(p.price)} · ${esc(size)}</span><div class="t3">${esc(p.address||"location pending")} · ${esc(p.listing_status||"status pending")} · risk ${esc(p.risk_score??"placeholder")}</div>`;
  place(x,y);
}
function showEntityAssetTip(p,x,y){
  let rel=p.asset_relationship||{};
  if(typeof rel==="string"){ try{ rel=JSON.parse(rel); }catch(_err){ rel={}; } }
  tip.innerHTML=`<b>${esc(p.name||"Physical asset")}</b><span class="t2">${esc(p.asset_type||"asset")} · ${esc(rel.relationship_type||"connected")}</span><div class="t3">${esc(p.city||p.state||p.country||"location")} · ${esc(rel.status||"inferred")} · ${esc(rel.source||p.source||"source pending")} · confidence ${confidencePct(rel.confidence??p.confidence)}</div>`;
  place(x,y);
}
function highlightAssetCorporateNetwork(entities){
  const id=entities?.owner?.id||entities?.operator?.id;
  if(id&&byId[id]&&mapReady) applyMapSelection(id,sourceForEntity(id));
}
async function showFarmWidget(assetId){
  if(!assetId) return;
  assignSelected(null); assignManualSelectedId(null); assignGlobeSelectionLabel("");
  clearMapSelection();
  document.getElementById("stSel").textContent="Farm";
  detail.innerHTML=`<div class="hd"><div class="top"><div><h2>Loading farm…</h2><div class="tick">${esc(assetId)}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div></div>`;
  detail.classList.add("show");
  try{
    const res=await fetch(`/api/assets/${encodeURIComponent(assetId)}/due-diligence`,{cache:"no-store"});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data=await res.json(),a=data.asset||{},f=a.farm_profile||{},owner=data.owner||a.owner||{},entities=a.connected_entities||{};
    highlightAssetCorporateNetwork(entities);
    const location=[a.address,a.county,a.state,a.country].filter(Boolean).join(" · ")||"—";
    const history=listValue(f.past_activities).length?listValue(f.past_activities):listValue(f.crop_history);
    const sources=[a.source,f.source,...(a.permits||[]).map(p=>p.source)].filter(Boolean);
    document.getElementById("stSel").textContent=a.name||"Farm";
    detail.innerHTML=`<div class="hd"><div class="top"><div>
      <h2>${esc(a.name||"Farm parcel")}</h2><div class="tick">${esc(location)}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div>
      <span class="badge" style="background:rgba(34,197,94,.14);color:#86efac;">${esc(f.farm_type||a.asset_type||"farm")}</span><span class="badge outline">${esc(a.status||"status pending")}</span><span class="badge signal">${confidencePct(a.confidence)} confidence</span>
      <div class="meta"><div><span>Acres</span><b>${esc(f.acres||a.area_acres||"—")}</b></div><div><span>Owner</span><b>${esc(owner.name||a.owner_entity_id||"—")}</b></div><div><span>Listing status</span><b>${esc(a.listing_status||"not loaded")}</b></div><div><span>Last sale</span><b>${compactMoney(f.last_sale_price)}</b></div><div><span>Estimated value</span><b>${compactMoney(f.current_estimated_value)}</b></div><div><span>Yearly gain</span><b>${compactMoney(f.yearly_estimated_gain)}</b></div></div>
      </div><div class="body"><div class="farm-detail">
      <div class="kpis"><div class="kpi"><div class="v">${esc(f.estimated_yield||"—")}</div><div class="l">estimated annual yield</div></div><div class="kpi"><div class="v">${esc(f.soil_quality||a.soil_quality||"—")}</div><div class="l">soil quality</div></div><div class="kpi"><div class="v">${esc(a.risk_level||f.risk_score||"—")}</div><div class="l">flood/drought risk</div></div></div>
      <div class="meta"><div class="span2"><span>Water access</span><b>${esc(f.water_access||a.water_access||"—")}</b></div><div><span>Risk score</span><b>${esc(f.risk_score??"—")}</b></div><div class="span2"><span>Nearby roads / infrastructure</span><b>${esc(listValue(a.nearby_infrastructure).join(" · ")||"—")}</b></div><div><span>Data sources</span><b>${esc([...new Set(sources)].join(" · ")||"—")}</b></div></div>
      <div class="section-h">Crop / Activity History</div><div class="farm-history">${history.length?history.map(x=>`<span>${esc(x)}</span>`).join(""):`<span>not loaded yet</span>`}</div>
      <div class="section-h">Corporate Network</div><div class="meta"><div><span>Owner company</span><b>${esc(entities.owner?.name||owner.name||"Owner relationship unknown")}</b></div><div><span>Operator</span><b>${esc(entities.operator?.name||"Operator relationship unknown")}</b></div><div><span>Permit authority</span><b>${esc((entities.permit_authorities||[]).map(x=>x.entity?.name||x.source_id).join(" · ")||"not loaded")}</b></div></div>
      ${valuationBlock(assetId)}
      ${evidenceBlock("asset",assetId)}
      </div></div>`;
    hydrateValuation(assetId);
    hydrateEvidence("asset",assetId);
  }catch(err){
    detail.innerHTML=`<div class="hd"><div class="top"><div><h2>Farm unavailable</h2><div class="tick">${esc(String(err?.message||err))}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div></div>`;
  }
}
async function showIndustrialWidget(assetId){
  if(!assetId) return;
  assignSelected(null); assignManualSelectedId(null); assignGlobeSelectionLabel("");
  clearMapSelection();
  document.getElementById("stSel").textContent="Industrial";
  detail.innerHTML=`<div class="hd"><div class="top"><div><h2>Loading industrial asset…</h2><div class="tick">${esc(assetId)}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div></div>`;
  detail.classList.add("show");
  try{
    const res=await fetch(`/api/assets/${encodeURIComponent(assetId)}/due-diligence`,{cache:"no-store"});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data=await res.json(),a=data.asset||{},p=a.industrial_profile||{},owner=data.owner||a.owner||{},operator=data.operator||a.operator||{},entities=a.connected_entities||{};
    highlightAssetCorporateNetwork(entities);
    const sources=[a.source,p.source,...(data.permits||[]).map(x=>x.source)].filter(Boolean);
    document.getElementById("stSel").textContent=a.name||"Industrial";
    detail.innerHTML=`<div class="hd"><div class="top"><div>
      <h2>${esc(a.name||"Industrial asset")}</h2><div class="tick">${esc(assetLocation(a))}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div>
      <span class="badge" style="background:rgba(249,115,22,.14);color:#fdba74;">${esc(p.industrial_type||a.asset_type||"industrial")}</span><span class="badge outline">${esc(a.status||"status pending")}</span><span class="badge signal">${confidencePct(a.confidence)} confidence</span>
      <div class="meta"><div><span>Owner company</span><b>${esc(owner.name||a.owner_entity_id||"—")}</b></div><div><span>Operator</span><b>${esc(operator.name||a.operator_entity_id||"—")}</b></div><div><span>Project cost</span><b>${compactMoney(p.estimated_project_cost)}</b></div><div><span>Power capacity</span><b>${esc(p.power_capacity_mw??"—")} MW</b></div><div><span>Annual growth</span><b>${esc(p.annual_growth||"placeholder")}</b></div><div><span>Demand score</span><b>${esc(p.demand_score||"placeholder")}</b></div></div>
      </div><div class="body"><div class="farm-detail">
      <div class="section-h">Permits</div>${permitRows(data.permits||[])}
      <div class="meta"><div class="span2"><span>Nearby transmission</span><b>${esc(a.nearby_transmission||"not loaded")}</b></div><div><span>Tax incentives</span><b>${esc(a.tax_incentives||"placeholder")}</b></div><div class="span2"><span>Roads / rail / ports</span><b>${esc(a.nearby_logistics||"not loaded")}</b></div><div><span>Water access</span><b>${esc(a.nearby_water_access||"not loaded")}</b></div><div><span>Revenue estimate</span><b>${compactMoney(p.revenue_estimate)}</b></div><div><span>Operating cost</span><b>${compactMoney(p.operating_cost_estimate)}</b></div><div><span>Owner gain/loss</span><b>${compactMoney(p.owner_gain_loss_estimate)}</b></div><div><span>Data sources</span><b>${esc([...new Set(sources)].join(" · ")||"—")}</b></div></div>
      <div class="section-h">Corporate Network</div><div class="meta"><div><span>Owner company</span><b>${esc(entities.owner?.name||owner.name||"Owner relationship unknown")}</b></div><div><span>Operator</span><b>${esc(entities.operator?.name||operator.name||"Operator relationship unknown")}</b></div><div><span>Financiers</span><b>${esc((entities.financiers||[]).map(x=>x.entity?.name||x.source_id).join(" · ")||"not loaded")}</b></div><div><span>Suppliers / builders</span><b>${esc([...(entities.suppliers||[]),...(entities.builders||[])].map(x=>x.entity?.name||x.source_id).join(" · ")||"not loaded")}</b></div><div><span>Permit authority</span><b>${esc((entities.permit_authorities||[]).map(x=>x.entity?.name||x.source_id).join(" · ")||"not loaded")}</b></div><div><span>Regulator</span><b>${esc((entities.regulators||[]).map(x=>x.entity?.name||x.source_id).join(" · ")||"not loaded")}</b></div></div>
      ${valuationBlock(assetId)}
      ${evidenceBlock("asset",assetId)}
      </div></div>`;
    hydrateValuation(assetId);
    hydrateEvidence("asset",assetId);
  }catch(err){
    detail.innerHTML=`<div class="hd"><div class="top"><div><h2>Industrial asset unavailable</h2><div class="tick">${esc(String(err?.message||err))}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div></div>`;
  }
}
async function showGovernmentWidget(assetId){
  if(!assetId) return;
  assignSelected(null); assignManualSelectedId(null); assignGlobeSelectionLabel("");
  clearMapSelection();
  document.getElementById("stSel").textContent="Government";
  detail.innerHTML=`<div class="hd"><div class="top"><div><h2>Loading government facility…</h2><div class="tick">${esc(assetId)}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div></div>`;
  detail.classList.add("show");
  try{
    const res=await fetch(`/api/assets/${encodeURIComponent(assetId)}/due-diligence`,{cache:"no-store"});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data=await res.json(),a=data.asset||{},owner=data.owner||a.owner||{};
    highlightAssetCorporateNetwork(a.connected_entities||{owner});
    const sourceLink=a.public_source_url?`<a href="${esc(a.public_source_url)}" target="_blank" rel="noopener noreferrer">${esc(a.public_source_url)}</a>`:"—";
    document.getElementById("stSel").textContent=a.name||"Government";
    detail.innerHTML=`<div class="hd"><div class="top"><div>
      <h2>${esc(a.name||"Government facility")}</h2><div class="tick">${esc(assetLocation(a))}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div>
      <span class="badge" style="background:rgba(56,189,248,.14);color:#7dd3fc;">${esc(a.facility_type||"public facility")}</span><span class="badge outline">${esc(a.jurisdiction||"jurisdiction pending")}</span><span class="badge signal">${confidencePct(a.confidence)} confidence</span>
      <div class="meta"><div><span>Agency / jurisdiction</span><b>${esc(owner.name||a.jurisdiction||"—")}</b></div><div><span>Facility type</span><b>${esc(a.agency_type||a.facility_type||"—")}</b></div><div><span>Status</span><b>${esc(a.status||"—")}</b></div><div class="span2"><span>Address</span><b>${esc(a.address||"—")}</b></div><div><span>Public source</span><b>${sourceLink}</b></div></div>
      </div><div class="body"><div class="farm-detail">
      <div class="section-h">Related Permits</div>${permitRows(data.permits||[])}
      <div class="meta"><div><span>Regulatory zones</span><b>public placeholder</b></div><div><span>Nearby assets affected</span><b>not loaded</b></div><div><span>Source</span><b>${esc(a.source||"—")}</b></div></div>
      ${valuationBlock(assetId)}
      ${evidenceBlock("asset",assetId)}
      </div></div>`;
    hydrateValuation(assetId);
    hydrateEvidence("asset",assetId);
  }catch(err){
    detail.innerHTML=`<div class="hd"><div class="top"><div><h2>Government facility unavailable</h2><div class="tick">${esc(String(err?.message||err))}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div></div>`;
  }
}
async function showListingWidget(listingId){
  if(!listingId) return;
  assignSelected(null); assignManualSelectedId(null); assignGlobeSelectionLabel("");
  clearMapSelection();
  document.getElementById("stSel").textContent="Listing";
  detail.innerHTML=`<div class="hd"><div class="top"><div><h2>Loading listing…</h2><div class="tick">${esc(listingId)}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div></div>`;
  detail.classList.add("show");
  try{
    const res=await fetch(`/api/listings/${encodeURIComponent(listingId)}`,{cache:"no-store"});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data=await res.json(),l=data.listing||{},a=data.asset||{},entities=a.connected_entities||{};
    highlightAssetCorporateNetwork(entities);
    const size=l.acreage?`${l.acreage} acres`:(l.square_feet?`${Number(l.square_feet).toLocaleString()} sq ft`:"—");
    const sourceLink=l.listing_url?`<a href="${esc(l.listing_url)}" target="_blank" rel="noopener noreferrer">${esc(l.listing_url)}</a>`:esc(l.source||"public_seed");
    const owner=entities.owner?.name||a.owner?.name||"Owner relationship unknown";
    const operator=entities.operator?.name||a.operator?.name||"Operator relationship unknown";
    document.getElementById("stSel").textContent=l.title||"Listing";
    detail.innerHTML=`<div class="hd"><div class="top"><div>
      <h2>${esc(l.title||"Marketplace listing")}</h2><div class="tick">${esc(l.address||assetLocation(a)||"location pending")}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div>
      <span class="badge" style="background:rgba(245,158,11,.14);color:#fbbf24;">${esc(l.asset_type||"asset")}</span><span class="badge outline">${esc(l.listing_status||"status pending")}</span><span class="badge signal">${confidencePct(l.confidence)} confidence</span>
      <div class="meta"><div><span>Price</span><b>${compactMoney(l.price)}</b></div><div><span>Size</span><b>${esc(size)}</b></div><div><span>Zoning</span><b>${esc(l.zoning||"—")}</b></div><div><span>Seller</span><b>${esc(l.seller_name||"—")}</b></div><div><span>Broker</span><b>${esc(l.broker_name||"—")}</b></div><div><span>Source</span><b>${sourceLink}</b></div></div>
      </div><div class="body"><div class="farm-detail">
      <div class="section-h">Listing Due Diligence</div><div class="meta"><div><span>Last sale</span><b>${compactMoney(l.last_sale_price)}</b></div><div><span>Estimated value</span><b>${compactMoney(l.current_estimated_value)}</b></div><div><span>Annual yield / income</span><b>${esc(l.expected_yield||"placeholder")}</b></div><div><span>Yearly gain</span><b>${compactMoney(l.estimated_annual_gain)}</b></div><div class="span2"><span>Nearby infrastructure</span><b>${esc(l.nearby_infrastructure||"not loaded")}</b></div><div><span>Flood/weather risk</span><b>${esc(l.flood_risk||"placeholder")}</b></div><div><span>Crime aggregate</span><b>${esc(l.crime_aggregate_score??"placeholder")}</b></div><div><span>Environmental risk</span><b>${esc(l.environmental_risk||"placeholder")}</b></div><div><span>Ownership</span><b>${esc(owner)}</b></div></div>
      <div class="section-h">Corporate Network</div><div class="meta"><div><span>Owner company</span><b>${esc(owner)}</b></div><div><span>Operator</span><b>${esc(operator)}</b></div><div><span>Parent / subsidiaries</span><b>not loaded</b></div><div><span>Financiers</span><b>${esc((entities.financiers||[]).map(x=>x.entity?.name||x.source_id).join(" · ")||"not loaded")}</b></div><div><span>Suppliers / builders</span><b>${esc([...(entities.suppliers||[]),...(entities.builders||[])].map(x=>x.entity?.name||x.source_id).join(" · ")||"not loaded")}</b></div><div><span>Permit authority</span><b>${esc((entities.permit_authorities||[]).map(x=>x.entity?.name||x.source_id).join(" · ")||"not loaded")}</b></div><div><span>Regulatory authority</span><b>${esc((entities.regulators||[]).map(x=>x.entity?.name||x.source_id).join(" · ")||"not loaded")}</b></div><div><span>Related securities</span><b>not loaded</b></div></div>
      ${valuationBlock(l.asset_id||a.id)}
      ${evidenceBlock("listing",l.id)}
      <div class="section-h">Data Status</div><div class="story-meta">Listing data is mock final-schema data. No restricted real estate platform was scraped. Valuation is deterministic and assumption-based.</div>
      </div></div>`;
    hydrateValuation(l.asset_id||a.id);
    hydrateEvidence("listing",l.id);
  }catch(err){
    detail.innerHTML=`<div class="hd"><div class="top"><div><h2>Listing unavailable</h2><div class="tick">${esc(String(err?.message||err))}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div></div>`;
  }
}
async function openAssetWidget(assetId){
  try{
    const res=await fetch(`/api/assets/${encodeURIComponent(assetId)}`,{cache:"no-store"});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const asset=await res.json();
    if(asset.asset_type==="farm"||asset.asset_type==="agricultural_complex"||asset.asset_type==="parcel") return showFarmWidget(assetId);
    if(asset.asset_type==="government_facility") return showGovernmentWidget(assetId);
    return showIndustrialWidget(assetId);
  }catch(_err){
    showIndustrialWidget(assetId);
  }
}
function place(x,y){ tip.style.left=(x+15)+"px"; tip.style.top=(y+15)+"px"; tip.style.opacity=1; }
function hideTip(){ tip.style.opacity=0; }
function newsFreshDate(){ let out=""; Object.values(NEWS.items_by_node||{}).forEach(items=>items.forEach(x=>{ if(x.published&&x.published>out) out=x.published; })); return out||"—"; }
function latestRefreshDate(){
  return [META.built_at,META.contracts_as_of,META.prices_as_of,newsFreshDate()].filter(x=>x&&x!=="—").sort().pop()||"—";
}
function updateFresh(){ updateDataHealth(); }
function updateDataHealth(){
  const yearly=COMPANIES.filter(existsInYear);
  let city=0,country=0,unknown=0;
  yearly.forEach(c=>{ const loc=companyLoc(c); if(!loc) unknown++; else if(loc.source==="country_fallback") country++; else city++; });
  const evidenced=LINKS.filter(l=>l.src||l.source_url).length;
  document.getElementById("fresh").textContent=`HQ located ${(city+country).toLocaleString()} · HQ unknown ${unknown.toLocaleString()} needs data · city ${city.toLocaleString()} · country ${country.toLocaleString()} · evidence ${evidenced}/${LINKS.length} · refresh ${latestRefreshDate()}`;
}

/* ---------- globe ---------- */
const MAP_STYLE_URL="https://tiles.openfreemap.org/styles/liberty";
const TERRAIN_STATUS_URL="/api/reliefs/dem/status";
// Default globe terrain: AWS Terrain Tiles (Tilezen "Joerd" on AWS Open Data) —
// global z0–z15, terrarium-encoded, no API key. Local 3DEP tiles are opt-in.
const AWS_TERRAIN_TILEJSON={
  tiles:["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
  minzoom:0, maxzoom:15, tileSize:256, encoding:"terrarium",
  attribution:"Terrain: Tilezen/Mapzen, USGS 3DEP, SRTM, GMTED, ETOPO1 (AWS Open Data)"
};
function globeVisibleCompanies(){
  const located=[],unknown=[];
  COMPANIES.forEach(c=>{ if(!baseVisibleNode(c)) return; const loc=companyLoc(c); (loc?located:unknown).push(c); });
  return {located,unknown};
}
async function loadBaseMapStyle(){
  const res=await fetch(MAP_STYLE_URL,{cache:"force-cache"});
  if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return patchBaseMapStyle(await res.json());
}
function patchBaseMapStyle(style){
  const building=(style.layers||[]).find(layer=>layer.id==="building-3d");
  if(building?.paint){
    building.paint["fill-extrusion-base"]=["coalesce",["get","render_min_height"],0];
    building.paint["fill-extrusion-height"]=["coalesce",["get","render_height"],0];
  }
  (style.layers||[]).forEach(layer=>{
    if(Array.isArray(layer.filter)) layer.filter=coalesceNumericFilterGets(layer.filter);
  });
  return style;
}
function coalesceNumericFilterGets(expr){
  if(!Array.isArray(expr)) return expr;
  const [op,a,b]=expr;
  if([">",">=","<","<=","==","!="].includes(op)&&typeof b==="number"&&Array.isArray(a)&&a[0]==="get") return [op,["coalesce",a,0],b];
  return expr.map(coalesceNumericFilterGets);
}
function initMapGlobe(){
  if(map||mapInitPromise||!window.maplibregl) return;
  assignMapInitPromise(loadBaseMapStyle().catch(err=>{
    console.warn("base map style patch skipped",err);
    return MAP_STYLE_URL;
  }).then(createMapGlobe));
}
function createMapGlobe(style){
  const start=restoredView.mode==="globe"&&restoredView.map?restoredView.map:{};
  assignMap(new maplibregl.Map({
    container:"map",style,
    center:Array.isArray(start.center)?start.center:[-95,28],
    zoom:Number.isFinite(start.zoom)?start.zoom:1.45,
    bearing:Number.isFinite(start.bearing)?start.bearing:0,
    pitch:Number.isFinite(start.pitch)?start.pitch:0,
    minZoom:1,maxZoom:14,attributionControl:true
  }));
  configureMapGestures();
  map.on("style.load",()=>{
    map.setProjection({type:"globe"});
    normalizeBaseMapLabels();
    assignMapReady(true);
    addMapLayers();
    drawGlobe();
  });
  map.on("moveend",()=>{ queueSaveView(); updateDueDiligenceSources(); });
  map.on("error",e=>console.warn("map globe",e.error||e));
}
function configureMapGestures(){
  map.dragPan?.enable?.();
  map.dragRotate?.enable?.();
  map.scrollZoom?.enable?.();
  map.doubleClickZoom?.disable?.();
  map.boxZoom?.disable?.();
  map.keyboard?.disable?.();
  map.touchZoomRotate?.enable?.();
  map.touchZoomRotate?.disableRotation?.();
  map.touchPitch?.disable?.();
}
function normalizeBaseMapLabels(){
  const layers=map?.getStyle?.()?.layers||[];
  for(const layer of layers){
    if(layer.type!=="symbol"||!layer.id||["company-labels-major","company-labels-close","security-labels","manual-labels","company-cluster-count"].includes(layer.id)) continue;
    const source=layer.source||"";
    if(source==="companies"||source==="securities"||source==="manual-nodes") continue;
    if(!/label|place|settlement|country|state|city|town|village|road|water|marine|airport|park|poi/i.test(layer.id)) continue;
    try{
      map.setLayoutProperty(layer.id,"text-field",[
        "coalesce",
        ["get","name_en"],
        ["get","name:en"],
        ["get","name_en-US"],
        ["get","name"],
        ["get","ref"]
      ]);
    }catch(_){}
  }
}
async function loadMapData(){
  if(mapData.companies) return mapData;
  const [companies,securities,relationships,graphIndex,unknown]=await Promise.all([
    fetch("data/companies.geojson").then(r=>r.json()),
    fetch("data/securities.geojson").then(r=>r.json()),
    fetch("data/relationships.geojson").then(r=>r.json()),
    fetch("data/graph-index.json").then(r=>r.json()),
    fetch("data/location_unknown.json").then(r=>r.ok?r.json():[]),
  ]);
  Object.assign(mapData,{companies,securities,relationships,graphIndex,unknown});
  globe.unknownCount=unknown.length||0;
  return mapData;
}
function addMapLayers(){
  if(map.getSource("companies")) return;
  addPhysicalContextLayers();
  addDueDiligenceLayers();
  map.addSource("relationships",{type:"geojson",data:"data/relationships.geojson",promoteId:"id"});
  map.addSource("companies",{type:"geojson",data:"data/companies.geojson",promoteId:"id",cluster:true,clusterRadius:55,clusterMaxZoom:5});
  map.addSource("securities",{type:"geojson",data:"data/securities.geojson",promoteId:"id"});
  addRelationshipLayers();
  addCompanyClusterLayers();
  addCompanyNodeLayers();
  addSecurityLayers();
  addCompanyLabelLayers();
  addManualLayers();
  wireMapInteractions();
  applyProductPrefs();
  loadMapData().then(()=>drawGlobe()).catch(err=>console.warn("map data",err));
}
function firstSymbolLayerId(){
  return map.getStyle()?.layers?.find(layer=>layer.type==="symbol")?.id;
}
function setTerrainDemStatus(next){
  assignTerrainDemStatus({...terrainDemStatus,...next});
  renderDataLayerPresets();
}
async function zoomToTerrainDem(){
  await setMode("globe");
  if(!mapReady||!map){
    setTimeout(zoomToTerrainDem,700);
    return;
  }
  productPrefs.dataLayers["relief-terrain"]=true;
  productPrefs.dataLayers["relief-hillshade"]=true;
  productPrefs.engine.terrain=true;
  productPrefs.engine.terrainExaggeration=Math.max(Number(productPrefs.engine.terrainExaggeration||0),2.4);
  saveProductPrefs();
  renderDataLayerPresets();
  try{ await loadTerrainDemStatus(); }catch(_err){}
  applyDueDiligenceLayerVisibility();
  const tj=terrainDemStatus.tilejson||{},center=tj.center||[-84.5,33.5,9],bounds=tj.bounds;
  const focus=bounds?.length===4?[center[0],Math.min(bounds[3]-0.08,center[1]+0.38)]:[center[0],center[1]];
  if(map) map.easeTo({center:focus,zoom:10.7,pitch:68,bearing:24,duration:900});
  setTimeout(()=>applyDueDiligenceLayerVisibility(),900);
}
async function loadTerrainDemStatus(){
  if(terrainDemStatusPromise) return terrainDemStatusPromise;
  assignTerrainDemStatusPromise(fetch(TERRAIN_STATUS_URL,{cache:"no-store"})
    .then(r=>{ if(!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json(); })
    .then(status=>{
      const tilejson=status.tilejson||{};
      setTerrainDemStatus({state:status.available?"loaded":"DEM unavailable",count:status.available?1:0,error:status.available?"":(status.status||"DEM unavailable"),tilejson,coverageLabel:status.coverage_label||""});
      return status;
    })
    .catch(err=>{
      setTerrainDemStatus({state:"DEM unavailable",count:0,error:String(err?.message||err),tilejson:null});
      throw err;
    }));
  return terrainDemStatusPromise;
}
function addTerrainSource(tilejson){
  if(!map||map.getSource("terrain-dem")) return;
  const tiles=(tilejson.tiles||[]).map(url=>url.startsWith("http")?url:url);
  if(!tiles.length) throw new Error("DEM tilejson has no tiles");
  map.addSource("terrain-dem",{
    type:"raster-dem",
    tiles,
    bounds:tilejson.bounds,
    minzoom:tilejson.minzoom,
    maxzoom:tilejson.maxzoom,
    tileSize:256,
    encoding:tilejson.encoding||"mapbox",
    attribution:tilejson.attribution||"USGS 3DEP"
  });
  map.addLayer({id:"terrain-hillshade",type:"hillshade",source:"terrain-dem",layout:{visibility:"none"},paint:{
    "hillshade-shadow-color":"#3f4957","hillshade-highlight-color":"#ffffff","hillshade-accent-color":"#91a6be","hillshade-exaggeration":0.55
  }},firstSymbolLayerId());
}
function addPhysicalContextLayers(){
  if(!map||map.getSource("terrain-dem")) return;
  setTerrainDemStatus({state:"loading",error:""});
  // Default to AWS terrarium (global, no key); only use local 3DEP when opted in.
  if(productPrefs.terrainSource!=="local"){
    addTerrainSource(AWS_TERRAIN_TILEJSON);
    setTerrainDemStatus({state:"loaded",count:1,error:"",tilejson:AWS_TERRAIN_TILEJSON});
    applyDueDiligenceLayerVisibility();
    return;
  }
  loadTerrainDemStatus().then(status=>{
    if(!status.available||!status.tilejson) throw new Error(status.status||"DEM unavailable");
    addTerrainSource(status.tilejson);
    applyDueDiligenceLayerVisibility();
  }).catch(err=>{
    console.warn("terrain layer skipped",err);
    applyDueDiligenceLayerVisibility();
  });
}
function relationshipWidth(){
  return ["interpolate",["linear"],["coalesce",["get","confidence"],0.5],0,0.5,1,3];
}
function addRelationshipLayers(){
  map.addLayer({id:"relationship-lines",type:"line",source:"relationships",layout:{"line-join":"round","line-cap":"round"},paint:{
    "line-color":["match",["get","relationship"],"OWNS","#60a5fa","SUPPLIES","#f59e0b","FINANCES","#22c55e","PARTNERS_WITH","#a78bfa","CONTRACTS","#38bdf8","SAME_ISSUER","#fbbf24","GOVERNMENT_ACTION","#fb7185","#64748b"],
    "line-width":relationshipWidth(),"line-opacity":0.25
  }});
}
function addCompanyClusterLayers(){
  map.addLayer({id:"company-clusters",type:"circle",source:"companies",filter:["has","point_count"],paint:{
    "circle-color":["step",["get","point_count"],"#5aa2ff",50,"#2ec9a4",200,"#f0b341",1000,"#ff7f6e"],
    "circle-radius":["step",["get","point_count"],18,50,28,200,42,1000,58],
    "circle-stroke-color":"#ffffff","circle-stroke-width":1.5,"circle-opacity":.78
  }});
  map.addLayer({id:"company-cluster-count",type:"symbol",source:"companies",filter:["has","point_count"],layout:{"text-field":["get","point_count_abbreviated"],"text-size":13,"text-font":["Noto Sans Bold"]},paint:{"text-color":"#ffffff"}});
}
function nodeRadius(){
  return ["interpolate",["linear"],["coalesce",["get","degree"],1],1,4,25,8,100,14,300,24];
}
function addCompanyNodeLayers(){
  map.addLayer({id:"company-halo",type:"circle",source:"companies",filter:["!",["has","point_count"]],paint:{
    "circle-radius":["interpolate",["linear"],["coalesce",["get","degree"],1],1,10,100,30,300,50],
    "circle-color":"#60a5fa","circle-opacity":["case",["boolean",["feature-state","selected"],false],0.25,0]
  }});
  map.addLayer({id:"company-nodes",type:"circle",source:"companies",filter:["!",["has","point_count"]],paint:{
    "circle-radius":nodeRadius(),
    "circle-color":["match",["get","entity_type"],"Public","#60a5fa","Private","#cbd5e1","Government","#38bdf8","Historical","#d6b46a","#94a3b8"],
    "circle-opacity":["case",["==",["get","location_quality"],"country_centroid"],0.5,0.85],
    "circle-stroke-color":"#ffffff",
    "circle-stroke-width":["case",["boolean",["feature-state","selected"],false],3,["case",["==",["get","location_quality"],"country_centroid"],0.7,1]]
  }});
}
function addSecurityLayers(){
  map.addLayer({id:"security-nodes",type:"circle",source:"securities",minzoom:3.2,paint:{
    "circle-radius":["interpolate",["linear"],["coalesce",["get","degree"],1],1,3,25,5,100,9],
    "circle-color":"#fbbf24","circle-opacity":["case",["==",["get","location_quality"],"country_centroid"],0.35,0.72],
    "circle-stroke-color":["case",["boolean",["feature-state","selected"],false],"#ffffff","#78350f"],
    "circle-stroke-width":["case",["boolean",["feature-state","selected"],false],3,1]
  }});
}
function addCompanyLabelLayers(){
  map.addLayer({id:"company-labels-major",type:"symbol",source:"companies",minzoom:3,filter:["all",["!",["has","point_count"]],[">=",["coalesce",["get","degree"],0],80]],layout:{"text-field":["coalesce",["get","ticker"],["get","name"],""],"text-size":12,"text-offset":[0,1.2],"text-anchor":"top","text-font":["Noto Sans Regular"]},paint:{"text-color":"#e5e7eb","text-halo-color":"#020617","text-halo-width":1.5,"text-opacity":1}});
  map.addLayer({id:"company-labels-close",type:"symbol",source:"companies",minzoom:6,filter:["!",["has","point_count"]],layout:{"text-field":["coalesce",["get","name"],""],"text-size":11,"text-offset":[0,1.4],"text-anchor":"top","text-font":["Noto Sans Regular"]},paint:{"text-color":"#f8fafc","text-halo-color":"#020617","text-halo-width":1.5,"text-opacity":1}});
  map.addLayer({id:"security-labels",type:"symbol",source:"securities",minzoom:5.2,layout:{"text-field":["coalesce",["get","ticker"],["get","name"]],"text-size":10.5,"text-offset":[0,1.2],"text-anchor":"top","text-font":["Noto Sans Regular"]},paint:{"text-color":"#fde68a","text-halo-color":"#020617","text-halo-width":1.5,"text-opacity":1}});
}
function manualNodeFeatures(){
  return {type:"FeatureCollection",features:manualLayer.nodes.filter(n=>Number.isFinite(n.lat)&&Number.isFinite(n.lng)).map(n=>({type:"Feature",id:n.id,geometry:{type:"Point",coordinates:[n.lng,n.lat]},properties:n}))};
}
function objectLngLat(id){
  const manual=manualLayer.nodes.find(n=>n.id===id);
  if(manual) return [manual.lng,manual.lat];
  const feature=[...(mapData.companies?.features||[]),...(mapData.securities?.features||[])].find(f=>f.properties.id===id);
  if(feature) return feature.geometry.coordinates;
  const loc=companyLoc(byId[id]);
  return loc?[loc.lon,loc.lat]:null;
}
function manualEdgeFeatures(){
  return {type:"FeatureCollection",features:manualLayer.edges.map(e=>{
    const a=objectLngLat(e.from),b=objectLngLat(e.to);
    return a&&b?{type:"Feature",id:e.id,geometry:{type:"LineString",coordinates:[a,b]},properties:e}:null;
  }).filter(Boolean)};
}
function updateManualLayer(){
  if(!mapReady) return;
  map.getSource("manual-nodes")?.setData(manualNodeFeatures());
  map.getSource("manual-edges")?.setData(manualEdgeFeatures());
}
function addManualLayers(){
  map.addSource("manual-edges",{type:"geojson",data:manualEdgeFeatures(),promoteId:"id"});
  map.addSource("manual-nodes",{type:"geojson",data:manualNodeFeatures(),promoteId:"id"});
  map.addLayer({id:"manual-edges",type:"line",source:"manual-edges",paint:{"line-color":"#ffffff","line-width":2,"line-dasharray":[2,2],"line-opacity":0.75}});
  map.addLayer({id:"manual-nodes",type:"circle",source:"manual-nodes",paint:{"circle-radius":9,"circle-color":productPrefs.engine.accent,"circle-stroke-color":"#ffffff","circle-stroke-width":2.5,"circle-opacity":0.92}});
  map.addLayer({id:"manual-labels",type:"symbol",source:"manual-nodes",minzoom:4,layout:{"text-field":["get","name"],"text-size":11,"text-offset":[0,1.35],"text-anchor":"top","text-font":["Noto Sans Regular"]},paint:{"text-color":"#ffffff","text-halo-color":"#020617","text-halo-width":1.5}});
}
function wireMapInteractions(){
  if(mapLayerEventsBound) return;
  assignMapLayerEventsBound(true);
  map.on("mouseenter","company-clusters",()=>map.getCanvas().style.cursor="pointer");
  map.on("mouseleave","company-clusters",()=>{ map.getCanvas().style.cursor=""; hideTip(); });
  const featureLayers=[
    ["company-nodes","companies"],["company-labels-major","companies"],["company-labels-close","companies"],
    ["security-nodes","securities"],["security-labels","securities"]
  ];
  const farmInteractiveLayers=["dd-farm-boundaries","dd-farm-complexes","dd-farm-crop-history","dd-farm-soil-quality","dd-farm-vegetation","dd-farm-acres","dd-farm-for-sale","dd-farm-yield","dd-farm-risk"].filter(id=>map.getLayer(id));
  const industrialInteractiveLayers=["dd-industrial-data-centers","dd-industrial-factories","dd-industrial-complexes","dd-industrial-energy","dd-industrial-hydro","dd-industrial-power-plants","dd-industrial-substations","dd-industrial-permits","dd-industrial-project-cost","dd-industrial-growth","dd-industrial-demand","dd-industrial-owner"].filter(id=>map.getLayer(id));
  const governmentInteractiveLayers=["dd-government-facilities","dd-government-agencies","dd-government-city-halls","dd-government-courthouses","dd-government-permits","dd-government-regulatory-zones","dd-government-restricted"].filter(id=>map.getLayer(id));
  const marketplaceInteractiveLayers=DATA_LAYER_PRESETS.find(p=>p.id==="marketplace").layers.flatMap(layer=>dataLayerMapIds(layer)).filter(id=>map.getLayer(id));
  const focusedAssetLayers=["selected-entity-assets","selected-entity-asset-fill"].filter(id=>map.getLayer(id));
  featureLayers.forEach(([layer,sourceId])=>{
    map.on("mouseenter",layer,()=>map.getCanvas().style.cursor="pointer");
    map.on("mouseleave",layer,()=>{ map.getCanvas().style.cursor=""; hideTip(); });
    map.on("mousemove",layer,e=>{ const c=byId[e.features[0].properties.id]; if(c) showNodeTip(c,e.originalEvent.clientX,e.originalEvent.clientY); });
    map.on("click",layer,e=>selectMapFeature(e.features[0],sourceId));
  });
  farmInteractiveLayers.forEach(layer=>{
    map.on("mouseenter",layer,()=>map.getCanvas().style.cursor="pointer");
    map.on("mouseleave",layer,()=>{ map.getCanvas().style.cursor=""; setFarmHover(""); hideTip(); });
    map.on("mousemove",layer,e=>{
      const p=e.features?.[0]?.properties||{};
      setFarmHover(p.id||"");
      showFarmTip(p,e.originalEvent.clientX,e.originalEvent.clientY);
    });
    map.on("click",layer,e=>showFarmWidget(e.features?.[0]?.properties?.id));
  });
  industrialInteractiveLayers.forEach(layer=>{
    map.on("mouseenter",layer,()=>map.getCanvas().style.cursor="pointer");
    map.on("mouseleave",layer,()=>{ map.getCanvas().style.cursor=""; hideTip(); });
    map.on("mousemove",layer,e=>showIndustrialTip(e.features?.[0]?.properties||{},e.originalEvent.clientX,e.originalEvent.clientY));
    map.on("click",layer,e=>{
      const p=e.features?.[0]?.properties||{};
      showIndustrialWidget(p.asset_id||p.id);
    });
  });
  governmentInteractiveLayers.forEach(layer=>{
    map.on("mouseenter",layer,()=>map.getCanvas().style.cursor="pointer");
    map.on("mouseleave",layer,()=>{ map.getCanvas().style.cursor=""; hideTip(); });
    map.on("mousemove",layer,e=>showGovernmentTip(e.features?.[0]?.properties||{},e.originalEvent.clientX,e.originalEvent.clientY));
    map.on("click",layer,e=>{
      const p=e.features?.[0]?.properties||{};
      if(p.asset_id||p.kind==="asset") showGovernmentWidget(p.asset_id||p.id);
    });
  });
  marketplaceInteractiveLayers.forEach(layer=>{
    map.on("mouseenter",layer,()=>map.getCanvas().style.cursor="pointer");
    map.on("mouseleave",layer,()=>{ map.getCanvas().style.cursor=""; hideTip(); });
    map.on("mousemove",layer,e=>showListingTip(e.features?.[0]?.properties||{},e.originalEvent.clientX,e.originalEvent.clientY));
    map.on("click",layer,e=>showListingWidget(e.features?.[0]?.properties?.id));
  });
  focusedAssetLayers.forEach(layer=>{
    map.on("mouseenter",layer,()=>map.getCanvas().style.cursor="pointer");
    map.on("mouseleave",layer,()=>{ map.getCanvas().style.cursor=""; hideTip(); });
    map.on("mousemove",layer,e=>showEntityAssetTip(e.features?.[0]?.properties||{},e.originalEvent.clientX,e.originalEvent.clientY));
    map.on("click",layer,e=>openAssetWidget(e.features?.[0]?.properties?.id));
  });
  if(map.getLayer("marketplace-clusters")){
    map.on("mouseenter","marketplace-clusters",()=>map.getCanvas().style.cursor="pointer");
    map.on("mouseleave","marketplace-clusters",()=>{ map.getCanvas().style.cursor=""; hideTip(); });
    map.on("mousemove","marketplace-clusters",e=>{ const p=e.features[0].properties; tip.innerHTML=`<b>${esc(p.point_count_abbreviated)} listings</b><span class="t2">Marketplace cluster</span><div class="t3">Click to zoom into individual assets</div>`; place(e.originalEvent.clientX,e.originalEvent.clientY); });
    map.on("click","marketplace-clusters",async e=>{
      const src=map.getSource("marketplace_listing_points"),id=e.features[0].properties.cluster_id;
      const zoom=await clusterCall(src,"getClusterExpansionZoom",id);
      if(Number.isFinite(zoom)) map.easeTo({center:e.features[0].geometry.coordinates,zoom:Math.min(zoom+.5,10),duration:420});
    });
  }
  map.on("mousemove","company-clusters",e=>{ const p=e.features[0].properties; tip.innerHTML=`<b>${esc(p.point_count_abbreviated)} companies</b><span class="t2">HQ cluster</span><div class="t3">Click to zoom and inspect</div>`; place(e.originalEvent.clientX,e.originalEvent.clientY); });
  map.on("click","company-clusters",e=>showMapCluster(e.features[0]));
  map.on("mouseenter","manual-nodes",()=>map.getCanvas().style.cursor="pointer");
  map.on("mouseleave","manual-nodes",()=>{ map.getCanvas().style.cursor=""; hideTip(); });
  map.on("mousemove","manual-nodes",e=>showManualTip(e.features[0].properties,e.originalEvent.clientX,e.originalEvent.clientY));
  map.on("click","manual-nodes",e=>showManualObject(e.features[0].properties.id));
  map.on("click",e=>{ if(!map.queryRenderedFeatures(e.point,{layers:[...featureLayers.map(x=>x[0]),...farmInteractiveLayers,...industrialInteractiveLayers,...governmentInteractiveLayers,...marketplaceInteractiveLayers,...focusedAssetLayers,"marketplace-clusters","company-clusters","manual-nodes"]}).length){ clearMapSelection(); deselect(); } });
}
function selectMapFeature(feature,sourceId){
  if(!feature?.properties?.id) return;
  select(feature.properties.id);
  applyMapSelection(feature.properties.id,sourceId);
}
function sourceForEntity(id){ return byId[id]?.kind==="security"?"securities":"companies"; }
function setLayerPaint(id,prop,value){ if(map?.getLayer(id)) map.setPaintProperty(id,prop,value); }
function applyMapSelection(id,sourceId=sourceForEntity(id)){
  if(!mapReady||!map?.getSource(sourceId)) return;
  if(mapSelectedId&&mapSelectedSource&&map.getSource(mapSelectedSource)) map.setFeatureState({source:mapSelectedSource,id:mapSelectedId},{selected:false});
  assignMapSelectedId(id); assignMapSelectedSource(sourceId);
  map.setFeatureState({source:sourceId,id},{selected:true});
  const focus=mapData.graphIndex?.[id]||{neighbors:[],edges:[]};
  const nodeIds=[id,...(focus.neighbors||[])],edgeIds=focus.edges||[];
  const nodeOpacity=["case",["in",["get","id"],["literal",nodeIds]],0.95,0.12];
  const labelOpacity=["case",["in",["get","id"],["literal",nodeIds]],1,0.15];
  setLayerPaint("company-nodes","circle-opacity",nodeOpacity);
  setLayerPaint("security-nodes","circle-opacity",nodeOpacity);
  setLayerPaint("company-labels-major","text-opacity",labelOpacity);
  setLayerPaint("company-labels-close","text-opacity",labelOpacity);
  setLayerPaint("security-labels","text-opacity",labelOpacity);
  setLayerPaint("relationship-lines","line-opacity",["case",["in",["get","id"],["literal",edgeIds]],0.9,0.04]);
  setLayerPaint("relationship-lines","line-width",["case",["in",["get","id"],["literal",edgeIds]],3.5,0.7]);
  setLayerPaint("company-clusters","circle-opacity",0.18);
}
function clearMapSelection(){
  if(!mapReady) return;
  if(mapSelectedId&&mapSelectedSource&&map.getSource(mapSelectedSource)) map.setFeatureState({source:mapSelectedSource,id:mapSelectedId},{selected:false});
  assignMapSelectedId(null); assignMapSelectedSource(null);
  setLayerPaint("company-nodes","circle-opacity",["case",["==",["get","location_quality"],"country_centroid"],0.5,0.85]);
  setLayerPaint("security-nodes","circle-opacity",["case",["==",["get","location_quality"],"country_centroid"],0.35,0.72]);
  setLayerPaint("company-labels-major","text-opacity",1);
  setLayerPaint("company-labels-close","text-opacity",1);
  setLayerPaint("security-labels","text-opacity",1);
  setLayerPaint("relationship-lines","line-opacity",0.25);
  setLayerPaint("relationship-lines","line-width",relationshipWidth());
  setLayerPaint("company-clusters","circle-opacity",0.78);
}
function clusterCall(src,name,...args){
  return new Promise(resolve=>{
    let done=false,finish=(err,val)=>{ if(!done){ done=true; resolve(err?null:val); } };
    const ret=src[name](...args,finish);
    if(ret&&ret.then) ret.then(v=>finish(null,v)).catch(err=>finish(err));
  });
}
async function showMapCluster(feature){
  const src=map.getSource("companies"),id=feature.properties.cluster_id,center=feature.geometry.coordinates;
  const zoom=await clusterCall(src,"getClusterExpansionZoom",id);
  if(Number.isFinite(zoom)) map.easeTo({center,zoom:Math.min(zoom+.6,8),duration:450});
  const total=Number(feature.properties.point_count)||100000;
  const leaves=await clusterCall(src,"getClusterLeaves",id,total,0);
  showMapClusterPanel(leaves||[],feature.properties.point_count_abbreviated||feature.properties.point_count||"");
}
function showMapClusterPanel(features,countLabel){
  assignMapClusterIds(features.map(f=>f.properties.id).filter(Boolean));
  assignSelected(null); assignGlobeSelectionLabel(`${countLabel} companies`); document.getElementById("stSel").textContent=globeSelectionLabel;
  const rows=mapClusterIds.map(id=>byId[id]).filter(Boolean).sort((a,b)=>(b.deg||0)-(a.deg||0)||a.n.localeCompare(b.n)).slice(0,60);
  detail.innerHTML=`<div class="hd"><div class="top"><div><h2>HQ cluster</h2><div class="tick">${esc(String(countLabel))} companies · ${rows.length<mapClusterIds.length?`showing ${rows.length} · `:""}zoom for city detail</div></div><button class="close" data-action="close-detail">&times;</button></div>
    <div class="detail-actions"><button class="primary" data-action="map-network">Network view</button></div></div>
    <div class="body"><div class="cluster-list">${rows.map(c=>`<button class="cluster-row" data-select-id="${esc(c.id)}"><span class="sw" style="background:${SECTORS[c.sec]?.color||"#9aa6b6"}"></span><span class="nm">${esc(c.n)}</span><span class="tag">${esc(companyLoc(c)?.label||displayLabel(c))}</span></button>`).join("")}</div></div>`;
  detail.classList.add("show");
}
async function networkFromMapIds(){
  assignNetworkScope(new Set(mapClusterIds)); assignSelected(null); await setMode("network");
}
function cleanLocText(v){ return String(v||"").replace(/\[[^\]]*\]/g,"").replace(/([A-Za-z])\d+\b/g,"$1").replace(/\s+/g," ").trim(); }
function locKey(v){ return cleanLocText(v).normalize("NFKD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/\./g,"").replace(/\s*,\s*/g,", "); }
function titleLoc(v){ return cleanLocText(v).replace(/\b\w/g,m=>m.toUpperCase()); }
function badHq(v){ return BAD_HQ_VALUES.has(locKey(v)); }
function locCountry(c,hq){
  if(c.country) return c.country;
  const last=cleanLocText(hq).split(",").pop()?.trim().toUpperCase();
  return COUNTRY_CODES[last]||"";
}
function coordCompatible(row,c,hq){
  const country=locKey(locCountry(c,hq)),hqKey=locKey(hq),region=locKey(row[3]||""),rowCountry=locKey(row[4]||"");
  if(country&&rowCountry) return country===rowCountry;
  if(region&&hqKey.includes(region)) return true;
  if(rowCountry&&hqKey.includes(rowCountry)) return true;
  return !hqKey.includes(",");
}
function coordRow(c,hq){
  const key=locKey(hq),country=locCountry(c,hq),countrySlug=locKey(country),countryKey=countrySlug&&key.endsWith(`, ${countrySlug}`)?key:(countrySlug?`${key}, ${countrySlug}`:"");
  if(countryKey&&HQ_CITY_COORDS[countryKey]) return HQ_CITY_COORDS[countryKey];
  if(HQ_CITY_COORDS[key]) return HQ_CITY_COORDS[key];
  const city=key.split(",")[0],row=city!==key?HQ_CITY_COORDS[city]:null;
  return row&&coordCompatible(row,c,hq)?row:null;
}
function companyLoc(c){
  if(c._loc!==undefined) return c._loc;
  const hq=cleanLocText(c.hq);
  const country=locCountry(c,hq);
  if(badHq(hq)){
    const fallback=COUNTRY_COORDS[country];
    return c._loc=fallback?{lat:fallback[0],lon:fallback[1],label:country,region:country,country,type:"HQ",source:"country_fallback",confidence:.35}:null;
  }
  const key=locKey(hq),city=key.split(",")[0];
  const row=coordRow(c,hq);
  if(row) return c._loc={lat:row[0],lon:row[1],label:row[2]||titleLoc(city),region:row[3]||row[2],country:row[4]||locCountry(c,hq),type:"HQ",source:row[5]||"hq_city",confidence:Number(row[6]??.9)};
  const fallback=COUNTRY_COORDS[country];
  if(fallback) return c._loc={lat:fallback[0],lon:fallback[1],label:country,region:country,country,type:"HQ",source:"country_fallback",confidence:.55};
  return c._loc=null;
}
function filteredFeatures(collection,predicate){
  return {type:"FeatureCollection",features:(collection?.features||[]).filter(predicate)};
}
function featureVisible(f){
  const c=byId[f.properties.id];
  return !!c&&baseVisibleNode(c);
}
function mapRelationshipVisible(f){
  const p=f.properties||{};
  return visibleEdgeRaw({from:p.from,to:p.to,rel:p.rel,start:p.start,end:p.end,as_of:p.as_of});
}
function updateMapSources(){
  if(!mapReady||!mapData.companies) return;
  map.getSource("companies")?.setData(filteredFeatures(mapData.companies,featureVisible));
  map.getSource("securities")?.setData(filteredFeatures(mapData.securities,featureVisible));
  map.getSource("relationships")?.setData(filteredFeatures(mapData.relationships,mapRelationshipVisible));
  updateManualLayer();
  if(mapSelectedId) requestAnimationFrame(()=>applyMapSelection(mapSelectedId,mapSelectedSource||sourceForEntity(mapSelectedId)));
}
function drawGlobe(){
  initMapGlobe();
  updateMapSources();
  const unknown=globe.unknownCount||mapData.unknown?.length||0;
  document.getElementById("stSel").textContent=selected?displayLabel(byId[selected]):(globeSelectionLabel||(unknown?unknown.toLocaleString()+" need location":"—"));
  updateDataHealth();
}
function focusGlobeOn(id){
  const feature=[...(mapData.companies?.features||[]),...(mapData.securities?.features||[])].find(f=>f.properties.id===id);
  const loc=feature?.geometry?.coordinates;
  if(map&&loc) map.easeTo({center:loc,zoom:Math.max(map.getZoom(),5),duration:550});
  else { const fallback=companyLoc(byId[id]); if(map&&fallback) map.easeTo({center:[fallback.lon,fallback.lat],zoom:Math.max(map.getZoom(),5),duration:550}); }
}
window.networkFromMapIds=networkFromMapIds;
window.mapState=()=>({
  ready:mapReady,
  selected:mapSelectedId,
  unknown:globe.unknownCount||mapData.unknown?.length||0,
  sources:(map?.getStyle?.()?.sources)?Object.keys(map.getStyle().sources):[],
  layers:map?.getStyle?.()?.layers?.map(l=>l.id)||[],
});

/* ---------- detail panel ---------- */
const detail=document.getElementById("detail");
const modeler=document.getElementById("modeler");
detail.addEventListener("click",e=>{
  const row=e.target.closest("[data-select-id]");
  if(row){ select(row.dataset.selectId); return; }
  const assetRow=e.target.closest("[data-asset-id]");
  if(assetRow){ openAssetWidget(assetRow.dataset.assetId); return; }
  const actionEl=e.target.closest("[data-action]");
  const action=actionEl?.dataset.action;
  if(!action) return;
  e.preventDefault();
  if(action==="close-detail") deselect();
  else if(action==="valuation-case"){
    const host=actionEl.closest("[data-valuation-asset]");
    if(host) hydrateValuation(host.dataset.valuationAsset,actionEl.dataset.case||"base");
  }
  else if(action==="valuation-save") saveValuationAssumptions(actionEl.closest("[data-valuation-asset]"));
  else if(action==="generate-report") generateReport(actionEl.dataset.objectType,actionEl.dataset.objectId);
  else if(action==="add-override") addOverride(actionEl.dataset.objectType,actionEl.dataset.objectId);
  else if(action==="delete-override") deleteOverride(actionEl.dataset.overrideId);
  else if(action==="map-network") networkFromMapIds();
  else if(action==="self-view") openSelfView(actionEl.dataset.id);
  else if(action==="financial-model") openModeler(actionEl.dataset.id);
  else if(action==="research") askAbout(actionEl.dataset.name,actionEl.dataset.ticker);
  else if(action==="manual-focus") focusManualObject(actionEl.dataset.id);
  else if(action==="manual-delete") deleteManualObject(actionEl.dataset.id);
});
modeler.addEventListener("click",async e=>{
  const actionEl=e.target.closest("[data-action]");
  const action=actionEl?.dataset.action;
  if(!action) return;
  e.preventDefault();
  e.stopPropagation();
  if(action==="close-modeler") closeModeler();
  if(action==="run-model") await runIntrinsicModel();
  if(action==="export-model") await exportDcfModel();
});
function displayLabel(c){ const short=c.n.length>12?c.n.slice(0,11)+"…":c.n; return (c.kind==="public"||c.kind==="security")&&c.t?c.t:short; }
function subtitle(c){
  if(c.kind==="public") return `${c.t} · CIK ${c.cik}`;
  if(c.kind==="security") return `${c.security_type_group||"Security"}${c.security_type?` · ${c.security_type.toUpperCase()}`:""}`;
  if(c.kind==="government") return "Government agency";
  if(c.kind==="legacy") return `Historical entity${c.end_date?` · ended ${c.end_date}`:""}`;
  return "Private company";
}
function entityTypeLabel(c){
  return DRAWER_TYPES[c.node_type]?.label||kindMeta[c.kind]?.name||"Entity";
}
function confidencePct(v){ const n=Number(v); return Number.isFinite(n)?`${Math.round(n*100)}%`:"—"; }
function confidenceBand(v){ const n=Number(v); if(!Number.isFinite(n)) return "Unknown"; if(n>=.85) return "High"; if(n>=.6) return "Medium"; return "Low"; }
function hqSummary(c){
  const loc=companyLoc(c);
  if(!loc) return {text:c.hq||"—",source:"unresolved",confidence:Number(c.location_confidence||0)};
  const parts=[loc.label,loc.region&&loc.region!==loc.label?loc.region:"",loc.country].filter(Boolean);
  return {text:parts.join(" · "),source:loc.source,confidence:Number(loc.confidence??c.location_confidence??0)};
}
function listingSummary(c){
  if(c.kind==="security") return [c.exchange,c.t,c.security_type_group].filter(Boolean).join(" · ")||"—";
  return [c.exchange,c.t||c.cik].filter(Boolean).join(" · ")||"—";
}
function latestFiling(c){
  return (c.filings||[]).slice().sort((a,b)=>String(b.filingDate||"").localeCompare(String(a.filingDate||"")))[0]||null;
}
function topCounterparties(inc,id,limit=5){
  const rows=new Map();
  inc.forEach(l=>{
    const other=byId[l.from===id?l.to:l.from];
    if(!other) return;
    const row=rows.get(other.id)||{node:other,value:0,count:0,rels:new Set(),edge:null};
    row.value+=Number(l.val||0); row.count+=1; row.rels.add(RELS[l.rel]?.name||l.rel);
    if(!row.edge||Number(l.confidence||0)>Number(row.edge.confidence||0)) row.edge=l; // representative (highest-confidence) edge
    rows.set(other.id,row);
  });
  return [...rows.values()].sort((a,b)=>(b.value-a.value)||(b.count-a.count)||a.node.n.localeCompare(b.node.n)).slice(0,limit);
}
function sourceDomain(url){ try{ return new URL(url).hostname.replace(/^www\./,""); }catch(_e){ return ""; } }
function confDotClass(v){ const n=Number(v); return n>=.85?"hi":n>=.6?"mid":"lo"; }
function provenanceHtml(edge){
  if(!edge) return "";
  const dom=sourceDomain(edge.source_url);
  const chip=edge.source_url&&dom?`<a class="src-chip" href="${esc(edge.source_url)}" target="_blank" rel="noopener noreferrer" title="${esc(edge.source_url)}">${esc(dom)}</a>`:"";
  const dot=`<span class="conf-dot ${confDotClass(edge.confidence)}" title="Confidence ${confidencePct(edge.confidence)}"></span>`;
  const date=edge.as_of?`<time class="as-of">${esc(edge.as_of)}</time>`:"";
  return `<div class="provenance">${dot}${chip}${date}</div>`;
}
function topCounterpartiesHtml(inc,id){
  const rows=topCounterparties(inc,id);
  if(!rows.length) return "";
  return `<div class="counterparties"><div class="section-h">Top counterparties</div><div class="counterparty-list">${rows.map(row=>`<div class="counterparty" data-select-id="${esc(row.node.id)}"><span class="sw" style="background:${SECTORS[row.node.sec]?.color||"#9aa6b6"}"></span><span class="nm">${esc(row.node.n)}</span><span class="why">${esc([...row.rels].slice(0,2).join(" / "))}${row.value>0?` · ${fmtBn(row.value)}`:""}</span>${provenanceHtml(row.edge)}</div>`).join("")}</div></div>`;
}
function modelBlock(c){
  if(!/^\d+$/.test(String(c.cik||""))) return ""; // no SEC facts -> no Model section
  return `<div class="counterparties" data-model="${esc(c.id)}"><div class="section-h">Model</div><div class="story-meta">Loading priced-in growth &amp; comps…</div></div>`;
}
async function loadModel(id){
  const host=document.querySelector(`[data-model="${CSS.escape(id)}"]`);
  if(!host) return;
  const [rd,cp]=await Promise.all([
    fetch(`/api/entity/${encodeURIComponent(id)}/reverse-dcf`).then(r=>r.json()).catch(()=>({available:false})),
    fetch(`/api/entity/${encodeURIComponent(id)}/comps?cap=8`).then(r=>r.json()).catch(()=>({available:false})),
  ]);
  if(!rd.available && !cp.available){ host.remove(); return; }
  let h=`<div class="section-h">Model</div>`;
  if(rd.available){
    h+=`<div class="model-line"><span>Priced-in growth</span><b>${(rd.implied_growth*100).toFixed(1)}%</b><span class="story-meta">@ ${(rd.discount*100).toFixed(0)}% disc · ${(rd.terminal_growth*100).toFixed(1)}% terminal</span></div>`;
    h+=`<div class="sens-row">${rd.sensitivity.map(s=>`<span class="sens">${(s.discount*100).toFixed(0)}%: ${s.implied_growth!=null?(s.implied_growth*100).toFixed(0)+"%":"—"}</span>`).join("")}</div>`;
  }
  if(cp.available && cp.peers.length){
    h+=`<div class="section-h">Comparables</div><div class="comps-list">`+cp.peers.map(p=>`<div class="comp-row" data-select-id="${esc(p.id)}"><span class="nm">${esc(p.ticker||p.name)}</span><span class="peer-chip ${esc(p.peer_source)}">${esc(p.peer_source)}</span><span class="why">${p.ebit_margin!=null?`${(p.ebit_margin*100).toFixed(0)}% mgn`:""}${p.ev_ebit!=null?` · ${p.ev_ebit.toFixed(0)}x EV/EBIT`:""}${p.pe!=null?` · ${p.pe.toFixed(0)} P/E`:""}</span></div>`).join("")+`</div>`;
  }
  host.innerHTML=h;
}
function companyAssetsBlock(id){
  return `<div class="counterparties" id="companyAssetsBlock" data-company-assets="${esc(id)}"><div class="section-h">Assets</div><div class="story-meta">Loading owned, operated, leased, financed, and supplied assets…</div></div>`;
}
async function loadCompanyAssets(id){
  const host=document.querySelector(`[data-company-assets="${CSS.escape(id)}"]`);
  if(!host) return;
  try{
    const res=await fetch(`/api/entity/${encodeURIComponent(id)}/assets`,{cache:"no-store"});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const filters=selectedEntityFilters();
    const rows=((await res.json()).assets||[]).filter(a=>{
      const rel=a.asset_relationship||{};
      if(filters.rel&&rel.relationship_type!==filters.rel) return false;
      if(filters.asset&&a.asset_type!==filters.asset) return false;
      if(Number(rel.confidence??a.confidence??0)<filters.confidence) return false;
      return true;
    });
    if(!rows.length){ host.innerHTML=`<div class="section-h">Assets</div><div class="story-meta">No mapped physical assets yet. Owner relationship unknown where not explicitly linked.</div>`; return; }
    host.innerHTML=`<div class="section-h">Assets</div><div class="counterparty-list">${rows.map(a=>{
      const rel=a.asset_relationship||{},value=(a.farm_profile?.current_estimated_value||a.industrial_profile?.estimated_project_cost||""),risk=(a.farm_profile?.risk_score??a.industrial_profile?.risk_score??"pending");
      return `<div class="counterparty" data-asset-id="${esc(a.id)}"><span class="sw" style="background:#f59e0b"></span><span class="nm">${esc(a.name||a.id)}</span><span class="why">${esc(rel.relationship_type||"CONNECTED")} · ${esc(a.asset_type||"asset")} · ${esc(a.city||a.state||a.country||"location")} · ${value?compactMoney(value):"value pending"} · ${esc(a.status||"status pending")} · risk ${esc(risk)} · ${confidencePct(rel.confidence??a.confidence)} · ${esc(rel.source||a.source||"source pending")} · ${esc(rel.status||"inferred")}</span></div>`;
    }).join("")}</div>`;
  }catch(err){
    host.innerHTML=`<div class="section-h">Assets</div><div class="story-meta">Could not load assets: ${esc(err.message||err)}</div>`;
  }
}
function select(id){
  assignManualSelectedId(null); assignSelected(id); assignGlobeSelectionLabel(""); const c=byId[id]; if(!nodeElsById[id]) buildNode(c); const lab=displayLabel(c); document.getElementById("stSel").textContent=lab;
  const inc=visibleEdges().filter(l=>l.from===id||l.to===id);
  const heldBy=inc.filter(l=>l.rel==="funds"&&l.to===id);
  const holds=inc.filter(l=>l.rel==="funds"&&l.from===id);
  const suppliedBy=inc.filter(l=>l.rel==="supplies"&&l.to===id);
  const suppliesTo=inc.filter(l=>l.rel==="supplies"&&l.from===id);
  const partners=inc.filter(l=>l.rel==="partners");
  const sameIssuer=inc.filter(l=>l.rel==="same_issuer");
  const contractFrom=inc.filter(l=>l.rel==="contracts"&&l.to===id);
  const contractTo=inc.filter(l=>l.rel==="contracts"&&l.from===id);
  const acquired=inc.filter(l=>l.rel==="acquired"&&l.from===id);
  const acquiredBy=inc.filter(l=>l.rel==="acquired"&&l.to===id);
  const owns=inc.filter(l=>l.rel==="owns"&&l.from===id);
  const ownedBy=inc.filter(l=>l.rel==="owns"&&l.to===id);
  const govActions=inc.filter(l=>l.rel==="government_action");
  const sum=a=>a.reduce((s,l)=>s+l.val,0);

  let kpis=[];
  if(contractFrom.length) kpis.push({v:sum(contractFrom)>0?fmtBn(sum(contractFrom)):contractFrom.length,l:"FY obligations to date"});
  if(contractTo.length) kpis.push({v:sum(contractTo)>0?fmtBn(sum(contractTo)):contractTo.length,l:"FY contractor links issued"});
  if(heldBy.length) kpis.push({v:fmtBn(sum(heldBy)),l:"held by mapped investors"});
  if(suppliesTo.length) kpis.push({v:fmtBn(sum(suppliesTo)),l:"mapped supply value (mixed basis)"});
  if(holds.length) kpis.push({v:fmtBn(sum(holds)),l:"mapped equity portfolio"});
  if(suppliedBy.length&&kpis.length<2) kpis.push({v:suppliedBy.length,l:"key suppliers mapped"});

  const sector=SECTORS[c.sec]||{name:c.sector||"Other",color:"#6b7682"};
  const km=kindMeta[c.kind]||{name:c.kind,color:"var(--text-2)"};
  const inbound=inc.filter(l=>l.to===id).length,outbound=inc.filter(l=>l.from===id).length;
  if(inc.length) kpis.unshift({v:inc.length,l:`visible links · ${inbound} in / ${outbound} out`});
  const issuerNode=c.kind==="security"?byId[c.issuer_id]:null;
  const issuerCell=issuerNode?`<b><a class="issuer-link" data-select-id="${esc(issuerNode.id)}" role="link" tabindex="0">${esc(issuerNode.n)}</a></b>`:`<b>${esc(c.issuer_id||"—")}</b>`;
  const securityMeta=c.kind==="security"?`<div><span>Security type</span><b>${esc(c.security_type_group||c.security_type||"Security")}</b></div><div><span>Issuer</span>${issuerCell}</div>`:"";
  const hq=hqSummary(c),filing=latestFiling(c),sourceConf=Number(c.source_confidence||0),p=c.price||{};
  let html=`<div class="hd"><div class="top"><div>
    <h2>${esc(c.n)}</h2><div class="tick">${esc(subtitle(c))}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div>
    <span class="badge" style="background:${sector.color}22;color:${sector.color};">${esc(sector.name)}</span><span class="badge outline">${esc(entityTypeLabel(c))}</span><span class="badge signal">${esc(confidenceBand(sourceConf))} confidence</span><span class="badge lens">${esc(LENSES[productPrefs.lens]?.[0]||"Company Research")}</span>
    <div class="meta"><div><span>Node type</span><b>${esc(entityTypeLabel(c))}</b></div><div><span>Listing</span><b>${esc(listingSummary(c))}</b></div><div><span>Connections</span><b>${inc.length} visible · ${c.deg||0} total</b></div><div class="span2"><span>Canonical HQ</span><b>${esc(hq.text)}</b></div><div><span>HQ source</span><b>${esc(hq.source)} · ${confidencePct(hq.confidence)}</b></div><div><span>Latest filing</span><b>${filing?`${esc(filing.form)} · ${esc(filing.filingDate)}`:"—"}</b></div><div><span>Recent price</span><b>${p.price!=null?`${fmtPrice(p.price)} · ${fmtPct(p.day_change_pct)}`:"—"}</b></div><div><span>Source confidence</span><b>${confidencePct(sourceConf)}</b></div>${securityMeta}<div><span>Group</span><b>${esc(c.group||"—")}</b></div><div><span>Sub-industry</span><b>${esc(c.sub||"—")}</b></div><div><span>Founded</span><b>${esc(c.f||"—")}</b></div><div><span>Ended</span><b>${esc(c.end_date||"—")}</b></div></div>
    <div class="detail-actions"><button class="primary" type="button" data-action="self-view" data-id="${esc(id)}">Self view</button><button type="button" data-action="financial-model" data-id="${esc(id)}">Financial Modeling</button></div></div><div class="body">`;
  if(kpis.length) html+=`<div class="kpis">${kpis.slice(0,3).map(x=>`<div class="kpi"><div class="v">${x.v}</div><div class="l">${x.l}</div></div>`).join("")}</div>`;
  if(sectionOn("counterparties")) html+=topCounterpartiesHtml(inc,id);
  html+=companyAssetsBlock(id);
  html+=modelBlock(c);
  if(sectionOn("lens")) html+=lensContextBlock(c,inc);
  if(sectionOn("relationships")) html+=`<div class="rels">`;
  const tot=inc.length;
  if(sectionOn("relationships")){
    if(!tot) html+=`<div class="empty">No visible relationships for this year and filter set. Structural edges are shown only when a source, generated overlay, or curated record exists.</div>`;
    html+=grp("Government contracts from",contractFrom,id,RELS.contracts?.color||"#58c7f3");
    html+=grp("Contracts issued to",contractTo,id,RELS.contracts?.color||"#58c7f3");
    html+=grp("Supplied by",suppliedBy,id,"#2ec9a4");
    html+=grp("Supplies to",suppliesTo,id,"#2ec9a4");
    html+=grp("Held by",heldBy,id,"#f0b341");
    html+=grp("Holdings",holds,id,"#f0b341");
    html+=grp("Partners",partners,id,"#9b8cff");
    html+=grp("Same issuer / listing",sameIssuer,id,RELS.same_issuer?.color||"#7fb3ff");
    html+=grp("Owns",owns,id,RELS.owns?.color||"#d0a7ff");
    html+=grp("Owned by",ownedBy,id,RELS.owns?.color||"#d0a7ff");
    html+=grp("Acquired / absorbed",acquired,id,RELS.acquired?.color||"#c6a15b");
    html+=grp("Acquired by",acquiredBy,id,RELS.acquired?.color||"#c6a15b");
    html+=grp("Government action",govActions,id,RELS.government_action?.color||"#ff7f6e");
    html+=`</div>`;
  }
  html+=`${evidenceBlock("entity",id)}${sectionOn("candidates")?candidateBlock(c):""}${sectionOn("market")?marketBlock(c):""}${sectionOn("filings")?filingsBlock(c):""}${sectionOn("research")?researchBlock(c):""}${sectionOn("news")?newsBlock(c):""}</div>`;
  detail.innerHTML=html; detail.classList.add("show"); document.getElementById("hint").style.display="none"; loadCompanyAssets(id); loadModel(id); hydrateEvidence("entity",id); loadCompanyAssetOverlay(id); draw(); if(mode==="globe") applyMapSelection(id,sourceForEntity(id)); queueSaveView();
}
function lensContextBlock(c,inc){
  const lens=productPrefs.lens;
  if(lens==="political"){
    const gov=inc.filter(l=>l.rel==="contracts"||l.rel==="government_action");
    return `<div class="lens-context"><div class="section-h">Political exposure lens</div><div class="market-card">Public overlap only. Contracts/actions visible now: <b>${gov.length}</b>. No corruption inference is made; timing and source evidence must carry the claim.</div></div>`;
  }
  if(lens==="facility"||lens==="farm"||lens==="acquisition"){
    return `<div class="lens-context"><div class="section-h">${esc(LENSES[lens][0])}</div><div class="market-card">Use Maker to add manual sites, parcels, farms, routes, or opportunities around this object. Public enrichment waits until the local map is useful.</div></div>`;
  }
  if(lens==="security"&&c.kind!=="security") return "";
  return `<div class="lens-context"><div class="section-h">${esc(LENSES[lens]?.[0]||"Company Research")}</div><div class="market-card">${esc(LENSES[lens]?.[1]||"Object evidence and relationships.")}</div></div>`;
}
function grp(title,arr,id,color){
  if(!arr.length) return "";
  let h=`<div class="group"><div class="group-h"><span class="ln" style="border-color:${color}"></span>${esc(title)} (${arr.length})</div>`;
  arr.forEach(l=>{ const other=byId[l.from===id?l.to:l.from];
    const dateBits=edgeDateText(l);
    const conf=l.confidence?` · confidence ${Math.round(l.confidence*100)}%`:"";
    const src=l.source_url?`<a href="${esc(l.source_url)}" target="_blank" rel="noopener noreferrer">${esc(l.src||"source")}</a>`:esc(l.src||"source");
    h+=`<div class="item" data-select-id="${esc(other.id)}"><span class="sw" style="background:${SECTORS[other.sec].color}"></span><span class="nm">${esc(other.n)}</span>${l.val>0?`<span class="val">${fmtBn(l.val)}</span>`:""}</div><div class="meta-row">${esc(l.detail||"")}${dateBits?` · ${esc(dateBits)}`:""}${conf}</div><div class="src">${src}</div>`; });
  return h+`</div>`;
}
function edgeDateText(l){
  if(l.start&&l.end) return `period ${l.start} to ${l.end}${l.as_of?` · reported ${l.as_of}`:""}`;
  if(l.start) return `happened ${l.start}`;
  if(l.as_of) return `reported ${l.as_of}`;
  return "";
}
function deriveResearch(c){
  if(c.research) return c.research;
  const cik=c.cik, t=c.t||c.id, n=c.n||"";
  if(!cik) return {};
  const cikInt=String(parseInt(cik,10));
  return {
    sec_filings:`https://www.sec.gov/edgar/browse/?CIK=${cikInt}`,
    sec_10k:`https://www.sec.gov/edgar/search/#/dateRange=all&forms=10-K%2C10-Q&entityName=${encodeURIComponent(t||n)}`,
    companyfacts:`https://data.sec.gov/api/xbrl/companyfacts/CIK${cik}.json`,
    usaspending:`https://www.usaspending.gov/search/?hash=a1b2c3&filters=%7B%22keyword%22%3A%22${encodeURIComponent(n)}%22%7D`,
    news:`https://news.google.com/rss/search?q=${encodeURIComponent(n+(t?" "+t:""))}`,
  };
}
function researchBlock(c){
  const labels={sec_filings:"SEC filings",sec_10k:"10-K / 10-Q",companyfacts:"XBRL facts",quote:"Market quote",website:"Company site",usaspending:"USAspending",news:"News"};
  const research=deriveResearch(c);
  const links=Object.entries(research).filter(([k,v])=>labels[k]&&v);
  if(!links.length) return "";
  return `<div class="research"><div class="section-h">Research</div><div class="link-grid">${links.map(([k,v])=>`<a href="${esc(v)}" target="_blank" rel="noopener noreferrer">${labels[k]}</a>`).join("")}</div></div>`;
}
function sparkline(values){
  const nums=(values||[]).map(Number).filter(Number.isFinite);
  if(nums.length<2) return "";
  const w=260,h=36,p=3,min=Math.min(...nums),max=Math.max(...nums),span=max-min||1;
  const pts=nums.map((v,i)=>`${(i/(nums.length-1)*w).toFixed(1)},${(h-p-((v-min)/span)*(h-p*2)).toFixed(1)}`).join(" ");
  return `<svg class="spark ${nums.at(-1)>=nums[0]?"up":"down"}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}"></polyline></svg>`;
}
function marketBlock(c){
  const p=c.price;
  if(!p||p.price==null) return "";
  const day=Number(p.day_change_abs);
  const cls=day<0?"down":"up";
  return `<div class="market"><div class="section-h">Market</div><div class="market-card">
    <div class="market-top"><div class="market-price">${fmtPrice(p.price)}</div><div class="market-move ${cls}">${fmtSignedMoney(p.day_change_abs)} (${fmtPct(p.day_change_pct)})</div></div>
    <div class="market-sub"><span>6M ${fmtPct(p.chg_6m_pct)}</span><span>${esc(p.as_of||"—")} · ${esc(p.source||"price source")}</span></div>
    ${sparkline(p.spark)}</div></div>`;
}
function filingsBlock(c){
  const items=c.filings||[];
  if(!items.length) return "";
  return `<div class="research"><div class="section-h">Latest filings</div><div class="link-grid">${items.map(x=>`<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.form)} · ${esc(x.filingDate)}</a>`).join("")}</div></div>`;
}
function newsBlock(c){
  const items=(NEWS.items_by_node||{})[c.id]||[];
  if(!items.length) return "";
  return `<div class="news"><div class="section-h">Recent news</div>${items.slice(0,4).map(x=>`<a class="story" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer"><div class="story-title">${esc(x.title)}</div><div class="story-meta">${esc(x.source||"News")} · ${esc(x.published||"")}</div></a>`).join("")}</div>`;
}
function candidateBlock(c){
  const items=EDGE_CANDIDATES.filter(x=>x.status==="candidate"&&(x.from===c.id||x.to===c.id));
  if(!items.length) return "";
  return `<div class="candidates"><div class="section-h">Candidate signals</div>${items.slice(0,5).map(x=>{ const other=byId[x.from===c.id?x.to:x.from]; return `<a class="story" href="${esc(x.source_url)}" target="_blank" rel="noopener noreferrer"><div class="story-title">${esc(RELS[x.rel]?.name||x.rel)} · ${esc(other?.n||x.to||x.from)}</div><div class="story-meta">${esc(x.detail||"")}</div><div class="story-meta">${esc(x.src||"candidate")} · ${esc(x.as_of||x.start||"")}</div></a>`; }).join("")}</div>`;
}
function fmtLargeMoney(v){
  const n=Number(v);
  if(!Number.isFinite(n)) return "—";
  const a=Math.abs(n),sign=n<0?"-":"";
  if(a>=1e12) return `${sign}$${(a/1e12).toFixed(2)}T`;
  if(a>=1e9) return `${sign}$${(a/1e9).toFixed(2)}B`;
  if(a>=1e6) return `${sign}$${(a/1e6).toFixed(1)}M`;
  return `${sign}$${Math.round(a).toLocaleString()}`;
}
function openModeler(id){
  const c=byId[id||selected];
  if(!c) return;
  const issuer=c.issuer_id&&byId[c.issuer_id]?byId[c.issuer_id]:c;
  const disabled=["Residual Income","Earnings-Based","Accounting Asset Approaches","Economic Asset Approaches","Bayesian Methods","Option-Based Valuation","Stochastic Processes","Private Equity / LBO","Sector-Specific: Insurance","Sector-Specific: REITs","Sector-Specific: Energy / Mining","Sector-Specific: Biotech","Hybrid Methods"];
  modeler.dataset.id=issuer.id;
  modeler.innerHTML=`<div class="hd"><div class="top"><div><h3>Financial Modeling</h3><div class="sub">${esc(c.id===issuer.id?c.n:`${c.n} · issuer model: ${issuer.n}`)}</div></div><button class="close" type="button" data-action="close-modeler">&times;</button></div></div>
    <div class="body"><div class="section-h">Intrinsic Valuation Model</div>
    <div class="choice"><label><span>Cash Flow Based</span><input type="radio" name="valuation-method" value="cash_flow" checked></label><label><span>Dividend Based</span><input type="radio" name="valuation-method" value="dividend"></label></div>
    <button class="primary" type="button" data-action="export-model">Export selected DCF to Excel</button>
    <button type="button" data-action="run-model" style="margin-top:8px;">Quick browser estimate</button>
    <div id="modelResult" class="result">Excel export uses backend SEC companyfacts. Estimated time: 5-15 seconds when cached, 30-90 seconds if the SEC facts file must be fetched first. Keep this tab open while the workbook is prepared.</div>
    <div class="section-h">Later models</div><div class="choice">${disabled.map(x=>`<div class="locked"><span>${esc(x)}</span><span>Later</span></div>`).join("")}</div></div>`;
  modeler.classList.add("show");
  queueSaveView();
}
function closeModeler(){ modeler.classList.remove("show"); queueSaveView(); }
function dcfApiBase(){ return location.port==="8788"?location.origin:"http://127.0.0.1:8788"; }
function dcfFilename(c,method){
  return `${String(c.t||c.id||"entity").replace(/[^A-Za-z0-9_-]+/g,"_")}_${method}_dcf.xlsx`;
}
async function exportDcfModel(){
  const c=byId[modeler.dataset.id],out=document.getElementById("modelResult");
  if(!c||!out) return;
  const method=modeler.querySelector("input[name='valuation-method']:checked")?.value||"cash_flow";
  out.innerHTML=`<b>Preparing ${esc(method==="dividend"?"Dividend Based":"Cash Flow Based")} DCF workbook...</b><br>Estimated time: 5-15 seconds if cached, 30-90 seconds on first SEC fetch.`;
  try{
    const res=await fetch(`${dcfApiBase()}/api/entity/${encodeURIComponent(c.id)}/dcf.xlsx?method=${encodeURIComponent(method)}`);
    if(!res.ok){
      let message=res.statusText;
      try{ message=(await res.json()).error||message; }catch(_err){}
      throw new Error(message||`HTTP ${res.status}`);
    }
    const blob=await res.blob();
    const url=URL.createObjectURL(blob);
    const a=document.createElement("a");
    a.href=url; a.download=dcfFilename(c,method); document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
    out.innerHTML=`<b>Excel export ready.</b><br>${esc(a.download)} was generated from SEC companyfacts with editable assumptions and audit/source sheets.`;
  }catch(err){
    out.innerHTML=`<b>Excel export backend is offline or missing data.</b><br>${esc(err.message||err)}<br>Start the app with <code>python3 map_api.py</code>, then open <code>http://127.0.0.1:8788/index.html</code> and try again.`;
  }
}
function latestFact(payload,names){
  const facts=payload?.facts?.["us-gaap"]||{};
  for(const name of names){
    const units=facts[name]?.units||{};
    const rows=Object.values(units).flat().filter(x=>Number.isFinite(Number(x.val))&&x.end);
    const annual=rows.filter(x=>x.fp==="FY"||x.form==="10-K"||(x.start&&x.end&&(new Date(x.end)-new Date(x.start))>300*864e5));
    const picked=annual.length?annual:rows;
    picked.sort((a,b)=>String(b.end).localeCompare(String(a.end))||String(b.filed||"").localeCompare(String(a.filed||"")));
    if(picked[0]) return {name,value:Number(picked[0].val),end:picked[0].end};
  }
  return null;
}
function cik10(c){ const digits=String(c?.cik||"").replace(/\D/g,""); return digits?digits.padStart(10,"0"):""; }
async function loadCompanyFacts(c){
  const cik=cik10(c);
  if(cik){
    const local=await fetch(`data/companyfacts/CIK${cik}.json`,{cache:"force-cache"}).catch(()=>null);
    if(local?.ok) return local.json();
  }
  const research=deriveResearch(c);
  if(!research.companyfacts) throw new Error("No SEC companyfacts URL is available for this entity.");
  const direct=await fetch(research.companyfacts,{cache:"force-cache"});
  if(!direct.ok) throw new Error(`SEC returned ${direct.status}`);
  return direct.json();
}
async function runIntrinsicModel(){
  const c=byId[modeler.dataset.id];
  const out=document.getElementById("modelResult");
  if(!c||!out) return;
  const method=modeler.querySelector("input[name='valuation-method']:checked")?.value||"cash_flow";
  out.textContent="Loading local SEC facts cache and building the intrinsic model...";
  try{
    const payload=await loadCompanyFacts(c);
    const cfo=latestFact(payload,["NetCashProvidedByUsedInOperatingActivities","NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]);
    const capex=latestFact(payload,["PaymentsToAcquirePropertyPlantAndEquipment","PaymentsToAcquireProductiveAssets"]);
    const divs=latestFact(payload,["PaymentsOfDividendsCommonStock","PaymentsOfDividends","CommonStockDividendsPerShareDeclared"]);
    const discount=.10,growth=.025;
    let basis,label,modelValue;
    if(method==="dividend"){
      basis=divs?Math.abs(divs.value):NaN; label="latest dividend cash paid";
    } else {
      basis=cfo&&capex?cfo.value-Math.abs(capex.value):NaN; label="latest free cash flow estimate";
    }
    modelValue=Number.isFinite(basis)?Math.max(0,basis*(1+growth)/(discount-growth)):NaN;
    out.innerHTML=Number.isFinite(modelValue)
      ? `<b>${esc(method==="dividend"?"Dividend-based intrinsic value":"Cash-flow intrinsic value")}: ${fmtLargeMoney(modelValue)}</b><br>${esc(label)}: ${fmtLargeMoney(basis)}<br>Assumptions: 10% discount rate, 2.5% terminal growth. Latest fact dates: CFO ${esc(cfo?.end||"—")}, capex ${esc(capex?.end||"—")}, dividends ${esc(divs?.end||"—")}.`
      : `SEC facts loaded, but the required ${method==="dividend"?"dividend":"cash flow and capex"} facts were not found for ${esc(c.n)}.`;
  } catch(err){
    out.textContent=`Could not load SEC companyfacts: ${err.message}. Cache this entity with: python3 cache_companyfacts.py ${c.t||c.cik}`;
  }
}
function deselect(){ assignSelected(null); assignManualSelectedId(null); assignGlobeSelectionLabel(""); assignSelectedEntityAssetFeatures([]); map?.getSource("selected_entity_assets")?.setData(EMPTY_GEOJSON); map?.getSource("selected_entity_asset_links")?.setData(EMPTY_GEOJSON); clearMapSelection(); detail.classList.remove("show"); closeModeler(); document.getElementById("stSel").textContent="—"; draw(); queueSaveView(); }
function openSelfView(id){ const u=new URL(location.href); u.search=""; u.searchParams.set("self",id); window.open(u.toString(),"_blank"); }
function askAbout(name,t){ window.open("https://claude.ai/new?q="+encodeURIComponent("Analyze "+name+" ("+t+"): public filings, ownership, suppliers, customers, government contracts, historical status, and relationship risks."),"_blank"); }
window.select=select; window.deselect=deselect; window.openSelfView=openSelfView; window.askAbout=askAbout;
window.stressIndex=async(n=50000)=>{
  await loadBulk();
  if(!byId.STRESS_0){
    const sec=Object.keys(SECTORS)[0]||"other";
    for(let i=0;i<n;i++){ const c={id:"STRESS_"+i,canonical_id:"STRESS_"+i,n:"Stress "+i,t:"S"+i,sec,sector:SECTORS[sec]?.name||"Other",sub:"Synthetic",hq:"—",cik:"—",f:"",kind:"public",status:"active",deg:0,tot:0,r:3,x:(i%250)*24,y:7000+Math.floor(i/250)*24}; c.ix=c.x; c.iy=c.y; COMPANIES.push(c); byId[c.id]=c; adj[c.id]=new Set(); }
    META.companies=COMPANIES.length; buildGrid();
  }
  await setMode("index");
  return {nodes:COMPANIES.length,svgNodes:document.querySelectorAll("#nodes .node-g").length};
};
window.graphState=()=>({mode,companies:COMPANIES.length,bulkLoaded,selected,manualSelectedId,manualNodes:manualLayer.nodes.length,lens:productPrefs.lens,selfViewId,selfViewNodes:selfViewNodes.size,svgNodes:document.querySelectorAll("#nodes .node-g").length,canvasDisplay:getComputedStyle(canvas).display,stats:document.getElementById("stNodes").textContent});
window.graphPoint=id=>{ const c=byId[id],r=svg.getBoundingClientRect(); return c?{x:r.left+c.x*k+tx,y:r.top+c.y*k+ty}:null; };

/* ---------- product controls + manual layer ---------- */
const PALETTES={"Laser Red":"#ff3045","Signal White":"#f8fafc","Steel Blue":"#5aa2ff","Amber":"#f0b341","Emerald":"#2ec9a4","Bone":"#d8cab0"};
const LENSES={
  company:["Company Research","filings, prices, counterparties, evidence"],
  security:["Security Research","issuer, listing, security wrapper, filing links"],
  political:["Political Exposure","contracts, public-policy relevance, timing guardrails"],
  facility:["Facility Analysis","manual sites, power, permits, infrastructure notes"],
  farm:["Farm And Commodity","manual parcels, weather sensitivity, commodity assumptions"],
  acquisition:["Acquisition","targets, owners, routes, custom notes, export"]
};
function sectionOn(key){ return productPrefs.maker.sections[key]!==false; }
function setWorkspacePanel(name){
  assignActiveRailPanel(activeRailPanel===name?"":name);
  document.getElementById("workspacePanel").classList.toggle("show",!!activeRailPanel);
  document.querySelectorAll("#rail button, #gearPanel button[data-rail]").forEach(b=>b.classList.toggle("active",b.dataset.rail===activeRailPanel));
  renderWorkspacePanel();
}
function renderWorkspacePanel(){
  const panel=document.getElementById("workspacePanel");
  if(!activeRailPanel){ panel.innerHTML=""; return; }
  if(activeRailPanel==="engine"){
    panel.innerHTML=`<h3>Engine</h3><p>Global behavior and visual density.</p>
      <label class="control-row"><span>Accent</span><select data-engine="accent">${Object.entries(PALETTES).map(([n,v])=>`<option value="${v}" ${productPrefs.engine.accent===v?"selected":""}>${n}</option>`).join("")}</select></label>
      <label class="control-row"><span>Labels</span><select data-engine="labels">${["major","close","all","none"].map(v=>`<option value="${v}" ${productPrefs.engine.labels===v?"selected":""}>${v}</option>`).join("")}</select></label>
      <label class="control-row"><span>Node scale</span><input data-engine="nodeScale" type="range" min=".7" max="1.6" step=".05" value="${productPrefs.engine.nodeScale}"></label>
      <label class="control-row"><span>Line intensity</span><input data-engine="edgeOpacity" type="range" min=".35" max="1.8" step=".05" value="${productPrefs.engine.edgeOpacity}"></label>
      <label class="control-row"><span>Terrain / relief</span><input data-engine="terrain" type="checkbox" ${productPrefs.engine.terrain?"checked":""}></label>
      <label class="control-row"><span>Motion</span><input data-engine="motion" type="checkbox" ${productPrefs.engine.motion?"checked":""}></label>`;
    return;
  }
  if(activeRailPanel==="maker"){
    const sections=["counterparties","relationships","lens","candidates","market","filings","research","news"];
    panel.innerHTML=`<h3>Maker</h3><p>Choose what the object drawer shows and manage the local scenario layer.</p>
      ${sections.map(k=>`<label class="control-row"><span>${esc(k)}</span><input data-maker-section="${k}" type="checkbox" ${sectionOn(k)?"checked":""}></label>`).join("")}
      <button class="primary" type="button" data-action="manual-add-node">Add node at map center</button>
      <button type="button" data-action="manual-connect-selected">Connect selected object to latest node</button>
      <button type="button" data-action="manual-export-json">Export scenario JSON</button>
      <button type="button" data-action="manual-export-csv">Export nodes + edges CSV</button>
      <button type="button" data-action="manual-import-json">Import scenario JSON</button>
      <div class="manual-list">${manualLayer.nodes.slice(-8).reverse().map(n=>`<div class="manual-row" data-manual-id="${esc(n.id)}"><span>${esc(n.name)}</span><span>${esc(n.type||"custom")}</span></div>`).join("")||`<p>No manual objects yet.</p>`}</div>`;
    return;
  }
  if(activeRailPanel==="lenses"){
    panel.innerHTML=`<h3>Lenses</h3><p>Task presets, not raw settings.</p>${Object.entries(LENSES).map(([id,[name,desc]])=>`<div class="lens-pill ${productPrefs.lens===id?"active":""}" data-lens="${id}"><span>${name}</span><span>${desc}</span></div>`).join("")}`;
  }
}
async function addManualNodeAtCenter(){
  if(mode!=="globe") await setMode("globe");
  if(!map) return;
  const center=map.getCenter(),now=new Date().toISOString();
  const name=prompt("Manual object name", "NYC customer cluster");
  if(!name) return;
  const type=prompt("Object type", "customer_cluster")||"custom";
  manualLayer.nodes.push({id:`manual:${Date.now().toString(36)}`,name,type,lat:Number(center.lat.toFixed(6)),lng:Number(center.lng.toFixed(6)),source:"manual",confidence:.7,created_at:now,updated_at:now,notes:""});
  saveManualLayer(); updateManualLayer(); renderWorkspacePanel();
}
function connectSelectedToLatestManual(){
  const target=manualLayer.nodes.at(-1);
  if(!selected||!byId[selected]||!target){ alert("Select a public object and create a manual node first."); return; }
  const now=new Date().toISOString();
  manualLayer.edges.push({id:`manual_edge:${Date.now().toString(36)}`,from:selected,to:target.id,type:"exposed_to",source:"manual",confidence:.7,created_at:now,updated_at:now});
  saveManualLayer(); updateManualLayer(); renderWorkspacePanel();
}
function csv(rows){
  return rows.map(row=>row.map(v=>`"${String(v??"").replaceAll('"','""')}"`).join(",")).join("\n")+"\n";
}
function exportManualCsv(){
  downloadText("oasis_manual_nodes.csv",csv([["id","name","type","lat","lng","source","confidence","notes"],...manualLayer.nodes.map(n=>[n.id,n.name,n.type,n.lat,n.lng,n.source,n.confidence,n.notes])]),"text/csv");
  downloadText("oasis_manual_edges.csv",csv([["id","from","to","type","source","confidence"],...manualLayer.edges.map(e=>[e.id,e.from,e.to,e.type,e.source,e.confidence])]),"text/csv");
}
function showManualTip(n,x,y){
  tip.innerHTML=`<b>${esc(n.name)}</b><span class="t2">${esc(n.type||"manual object")} · manual layer</span><div class="t3">${esc(n.source||"manual")} · confidence ${confidencePct(n.confidence)}</div>`;
  place(x,y);
}
function showManualObject(id){
  const n=manualLayer.nodes.find(x=>x.id===id);
  if(!n) return;
  assignManualSelectedId(id); assignSelected(null); clearMapSelection();
  const edges=manualLayer.edges.filter(e=>e.from===id||e.to===id);
  document.getElementById("stSel").textContent=n.name;
  detail.innerHTML=`<div class="hd"><div class="top"><div><h2>${esc(n.name)}</h2><div class="tick">Manual object · ${esc(n.id)}</div></div><button class="close" type="button" data-action="close-detail">&times;</button></div>
    <span class="badge lens">User layer</span><span class="badge outline">${esc(n.type||"custom")}</span><span class="badge signal">${confidenceBand(n.confidence)} confidence</span>
    <div class="meta"><div><span>Object type</span><b>${esc(n.type||"custom")}</b></div><div><span>Location</span><b>${n.lat}, ${n.lng}</b></div><div><span>Source</span><b>${esc(n.source||"manual")}</b></div><div class="span2"><span>Notes</span><b>${esc(n.notes||"—")}</b></div><div><span>Edges</span><b>${edges.length}</b></div></div>
    <div class="detail-actions"><button class="primary" type="button" data-action="manual-focus" data-id="${esc(id)}">Focus map</button><button type="button" data-action="manual-delete" data-id="${esc(id)}">Delete</button></div></div>
    <div class="body"><div class="manual-detail"><div class="section-h">Manual relationships</div>${edges.map(e=>`<div class="story-title">${esc(e.type)} · ${esc(e.from===id?e.to:e.from)}</div>`).join("")||`<div class="empty">No manual edges yet.</div>`}</div></div>`;
  detail.classList.add("show"); queueSaveView();
}
function deleteManualObject(id){
  manualLayer.nodes=manualLayer.nodes.filter(n=>n.id!==id);
  manualLayer.edges=manualLayer.edges.filter(e=>e.from!==id&&e.to!==id);
  assignManualSelectedId(null); saveManualLayer(); updateManualLayer(); renderWorkspacePanel(); deselect();
}
function focusManualObject(id){
  const n=manualLayer.nodes.find(x=>x.id===id);
  if(n&&map) map.easeTo({center:[n.lng,n.lat],zoom:Math.max(map.getZoom(),6),duration:450});
}
function activateLens(id){
  if(!LENSES[id]) return;
  productPrefs.lens=id;
  saveProductPrefs(); renderWorkspacePanel();
  if(selected&&byId[selected]) select(selected);
}
function syncRailActive(){
  const byMode={globe:"map",network:"network",index:"network"};
  const active=activeRailPanel||byMode[mode]||"";
  document.querySelectorAll("#rail button").forEach(b=>b.classList.toggle("active",b.dataset.rail===active));
}
async function handleRailAction(r){
  if(r==="map"||r==="network"){
    assignActiveRailPanel("");
    document.getElementById("workspacePanel").classList.remove("show");
    renderWorkspacePanel();
    await setMode(r==="map"?"globe":"network");
    syncRailActive();
    return;
  }
  if(r==="research"){ selected&&byId[selected]?select(selected):searchInput.focus(); syncRailActive(); return; }
  if(r==="model"){ selected&&byId[selected]?openModeler(selected):setWorkspacePanel("maker"); syncRailActive(); return; }
  setWorkspacePanel(r); syncRailActive();
}
document.getElementById("rail").addEventListener("click",async e=>{
  const btn=e.target.closest("[data-rail]");
  if(!btn) return;
  await handleRailAction(btn.dataset.rail);
});
document.getElementById("gearPanel").addEventListener("click",async e=>{
  const btn=e.target.closest("[data-rail]");
  if(!btn) return;
  await handleRailAction(btn.dataset.rail);
});
document.getElementById("gearBtn").onclick=()=>toggleToolPanel("gearPanel");
document.getElementById("dataBtn").onclick=()=>toggleToolPanel("dataPanel");
document.getElementById("toolThemeBtn").onclick=function(){ const light=document.documentElement.getAttribute("data-theme")==="light"; document.documentElement.setAttribute("data-theme",light?"dark":"light"); syncThemeButton(); queueSaveView(); };
document.getElementById("toolGlobeBtn").onclick=()=>setMode("globe");
document.getElementById("toolModeBtn").onclick=()=>setMode(mode==="network"?"index":"network");
document.getElementById("dataPanel").addEventListener("change",e=>{
  const el=e.target;
  if(el.dataset.marketFilter){
    productPrefs.marketplace[el.dataset.marketFilter]=el.value;
    saveProductPrefs();
    loadDueDiligenceSource("marketplace_listings");
    queueSaveView();
    return;
  }
  if(el.dataset.assetGraphFilter){
    productPrefs.assetGraph[el.dataset.assetGraphFilter]=el.value;
    saveProductPrefs();
    refreshSelectedEntityAssetOverlay();
    if(selected) loadCompanyAssets(selected);
    renderDataLayerPresets();
    queueSaveView();
    return;
  }
  if(el.dataset.terrainExaggeration!==undefined){
    productPrefs.engine.terrainExaggeration=Number(el.value);
    saveProductPrefs();
    applyDueDiligenceLayerVisibility();
    renderDataLayerPresets();
    queueSaveView();
    return;
  }
  if(el.dataset.layerToggle){
    setDataLayer(el.dataset.layerToggle,el.checked);
    return;
  }
  const key=el.dataset.toolKind;
  if(!key) return;
  kindOn[key]=el.checked;
  refresh(true);
  buildToolKinds();
});
document.getElementById("dataPanel").addEventListener("input",e=>{
  const el=e.target;
  if(el.dataset.marketFilter){
    productPrefs.marketplace[el.dataset.marketFilter]=el.value;
    saveProductPrefs();
    clearTimeout(dueDiligenceLoadTimer);
    assignDueDiligenceLoadTimer(setTimeout(()=>loadDueDiligenceSource("marketplace_listings"),180));
    queueSaveView();
    return;
  }
  if(el.dataset.assetGraphFilter){
    productPrefs.assetGraph[el.dataset.assetGraphFilter]=el.value;
    el.closest(".marketplace-controls")?.querySelector(".terrain-control-row b")?.replaceChildren(`${Math.round(Number(el.value||0)*100)}%`);
    saveProductPrefs();
    refreshSelectedEntityAssetOverlay();
    if(selected) loadCompanyAssets(selected);
    queueSaveView();
    return;
  }
  if(el.dataset.terrainExaggeration===undefined) return;
  productPrefs.engine.terrainExaggeration=Number(el.value);
  el.closest(".terrain-controls")?.querySelector("b")?.replaceChildren(`${Number(el.value).toFixed(1)}x`);
  saveProductPrefs();
  applyDueDiligenceLayerVisibility();
  queueSaveView();
});
document.getElementById("dataPanel").addEventListener("click",e=>{
  const marketView=e.target.closest("[data-market-view]");
  if(marketView){
    productPrefs.marketplace.view=marketView.dataset.marketView;
    saveProductPrefs();
    renderDataLayerPresets();
    return;
  }
  const listing=e.target.closest("[data-listing-id]");
  if(listing){
    showListingWidget(listing.dataset.listingId);
    return;
  }
  const action=e.target.closest("[data-action]");
  if(action?.dataset.action==="zoom-terrain-dem"){
    zoomToTerrainDem();
    return;
  }
  const btn=e.target.closest("[data-layer-preset]");
  if(!btn) return;
  const id=btn.dataset.layerPreset;
  DATA_LAYER_OPEN[id]=!DATA_LAYER_OPEN[id];
  renderDataLayerPresets();
});
document.addEventListener("click",e=>{
  if(!document.body.contains(e.target)) return;
  if(e.target.closest("#gearBtn,#dataBtn,.tool-panel")) return;
  document.querySelectorAll(".tool-panel").forEach(p=>p.classList.remove("show"));
});
document.getElementById("workspacePanel").addEventListener("change",e=>{
  const el=e.target;
  if(el.dataset.engine){
    const k=el.dataset.engine;
    productPrefs.engine[k]=el.type==="checkbox"?el.checked:(el.type==="range"?Number(el.value):el.value);
    saveProductPrefs(); applyProductPrefs(); queueSaveView();
  }
  if(el.dataset.makerSection){
    productPrefs.maker.sections[el.dataset.makerSection]=el.checked;
    saveProductPrefs(); if(selected&&byId[selected]) select(selected);
  }
});
document.getElementById("workspacePanel").addEventListener("click",async e=>{
  const lens=e.target.closest("[data-lens]");
  if(lens){ activateLens(lens.dataset.lens); return; }
  const row=e.target.closest("[data-manual-id]");
  if(row){ showManualObject(row.dataset.manualId); return; }
  const action=e.target.closest("[data-action]")?.dataset.action;
  if(action==="manual-add-node") await addManualNodeAtCenter();
  if(action==="manual-connect-selected") connectSelectedToLatestManual();
  if(action==="manual-export-json") downloadText("oasis_manual_scenario.json",JSON.stringify(manualLayer,null,2),"application/json");
  if(action==="manual-export-csv") exportManualCsv();
  if(action==="manual-import-json") document.getElementById("manualImport").click();
});
document.getElementById("manualImport").addEventListener("change",async e=>{
  const file=e.target.files?.[0];
  if(!file) return;
  try{
    assignManualLayer(normalizeManualLayer(JSON.parse(await file.text())));
    saveManualLayer(); updateManualLayer(); renderWorkspacePanel();
  }catch(err){
    alert(`Could not import scenario JSON: ${err.message}`);
  }
  e.target.value="";
});

/* ---------- filters ---------- */
function buildFilters(){
  const sf=document.getElementById("sectorFilters");
  Object.entries(SECTORS).sort((a,b)=>a[1].name.localeCompare(b[1].name)).forEach(([key,v])=>{
    const count=COMPANIES.filter(c=>c.sec===key).length;
    const el=document.createElement("div"); el.className=`chip${sectorOn[key]?"":" off"}`; el.innerHTML=`<span class="sw" style="background:${v.color}"></span>${esc(v.name)}<span class="count">${count}</span>`;
    el.onclick=()=>{ sectorOn[key]=!sectorOn[key]; el.classList.toggle("off"); refresh(true); }; sf.appendChild(el);
  });
  const gf=document.getElementById("groupFilters");
  Object.entries(GROUPS).sort((a,b)=>a[1].name.localeCompare(b[1].name)).forEach(([key,v])=>{
    const count=COMPANIES.filter(c=>c.grp===key).length;
    const el=document.createElement("div"); el.className=`chip${groupOn[key]?"":" off"}`; el.innerHTML=`<span class="sw" style="background:${v.color}"></span>${esc(v.name)}<span class="count">${count}</span>`;
    el.onclick=()=>{ groupOn[key]=!groupOn[key]; el.classList.toggle("off"); refresh(true); }; gf.appendChild(el);
  });
  const rf=document.getElementById("relFilters");
  Object.entries(RELS).forEach(([key,v])=>{
    const count=LINKS.filter(l=>l.rel===key).length;
    const el=document.createElement("div"); el.className=`chip${relOn[key]?"":" off"}`; el.innerHTML=`<span class="ln" style="border-color:${v.color}"></span>${esc(v.name)}<span class="dir">${esc(v.dir||"")}</span>`;
    el.onclick=()=>{ relOn[key]=!relOn[key]; el.classList.toggle("off"); refresh(true); }; rf.appendChild(el);
  });
}
function buildToolKinds(){
  const host=document.getElementById("toolKindFilters");
  if(!host) return;
  host.innerHTML="";
  Object.keys(kindOn).sort((a,b)=>(kindMeta[a]?.name||a).localeCompare(kindMeta[b]?.name||b)).forEach(key=>{
    const meta=kindMeta[key]||{name:key,color:"#9aa6b6"};
    const count=COMPANIES.filter(c=>c.kind===key).length;
    const row=document.createElement("label");
    row.className="toggle-row";
    row.innerHTML=`<span><span class="sw" style="background:${meta.color};margin-right:8px"></span>${esc(meta.name)} <span style="color:var(--text-3)">(${count})</span></span><input type="checkbox" data-tool-kind="${esc(key)}" ${kindOn[key]?"checked":""}>`;
    host.appendChild(row);
  });
  renderDataLayerPresets();
}
function marketplaceControlsHtml(){
  const m=productPrefs.marketplace||{};
  const opt=(value,label)=>`<option value="${esc(value)}" ${m.asset_type===value?"selected":""}>${esc(label)}</option>`;
  const input=(key,ph,type="text")=>`<input ${type==="number"?"type=\"number\" min=\"0\" step=\"any\"":"type=\"text\""} data-market-filter="${esc(key)}" value="${esc(m[key]||"")}" placeholder="${esc(ph)}">`;
  return `<div class="marketplace-controls">
    <select data-market-filter="asset_type">${MARKETPLACE_ASSET_TYPES.map(x=>opt(x[0],x[1])).join("")}</select>
    ${input("location","Location")}
    <div class="marketplace-grid">${input("min_price","Min price","number")}${input("max_price","Max price","number")}${input("min_acres","Min acres","number")}${input("max_acres","Max acres","number")}${input("min_square_feet","Min sq ft","number")}${input("max_square_feet","Max sq ft","number")}</div>
    <div class="marketplace-grid">${input("zoning","Zoning")}${input("listing_status","Status")}${input("owner_type","Owner type")}${input("risk_max","Risk max","number")}${input("soil_quality_min","Soil min")}${input("infrastructure_distance_max","Infra miles max","number")}</div>
    <div class="marketplace-grid"><input disabled value="Expected yield placeholder"><input disabled value="Estimated gain placeholder"></div>
    <div class="marketplace-actions"><button type="button" data-market-view="cards" class="${m.view!=="table"?"active":""}">Cards</button><button type="button" data-market-view="table" class="${m.view==="table"?"active":""}">Table</button></div>
    <div id="marketplaceResults" class="marketplace-results">${marketplaceResultsHtml()}</div>
  </div>`;
}
function marketplaceResultsHtml(){
  const rows=[...marketplaceListings];
  const sort=productPrefs.marketplace?.sort||"price";
  rows.sort((a,b)=>sort==="price"?(Number(a.price||0)-Number(b.price||0)):String(a.title||"").localeCompare(String(b.title||"")));
  if(!rows.length) return `<div class="market-card-row"><span>No listings loaded for this view.</span></div>`;
  if(productPrefs.marketplace?.view==="table"){
    return rows.map(r=>`<div class="market-table-row" data-listing-id="${esc(r.id)}"><b>${esc(r.title||"Listing")}</b><span>${compactMoney(r.price)}</span><span>${esc(r.acreage?`${r.acreage} ac`:r.square_feet?`${r.square_feet} sf`:"—")}</span></div>`).join("");
  }
  return rows.map(r=>`<div class="market-card-row" data-listing-id="${esc(r.id)}"><b>${esc(r.title||"Listing")}</b><span>${esc(r.asset_type||"asset")} · ${compactMoney(r.price)} · ${esc(r.address||"")}</span></div>`).join("");
}
function renderMarketplaceResults(){
  const host=document.getElementById("marketplaceResults");
  if(host) host.innerHTML=marketplaceResultsHtml();
}
function assetGraphControlsHtml(){
  const f=productPrefs.assetGraph||{},relTypes=["","OWNS","OPERATES","LEASES","FINANCES","SUPPLIES","BUILDS","MANAGES","PERMITS","REGULATES","LOCATED_ON","CONNECTED_TO","NEAR","LISTED_AS"];
  const assetTypes=["","farm","data_center","factory","industrial_complex","government_facility","house","commercial_property","industrial_parcel","warehouse","franchise_location","data_center_site"];
  return `<section class="layer-preset open">
    <button class="preset-head" type="button" style="--layer-color:#60a5fa">
      <span class="layer-icon">${DATA_ICON_SVG.link}</span><span class="preset-title">Company Assets</span><span class="preset-meta">bridge</span><span class="preset-chevron">▾</span>
    </button>
    <div class="preset-body"><div class="marketplace-controls">
      <select data-asset-graph-filter="relationship_type">${relTypes.map(v=>`<option value="${esc(v)}" ${f.relationship_type===v?"selected":""}>${esc(v||"All relationship types")}</option>`).join("")}</select>
      <select data-asset-graph-filter="asset_type">${assetTypes.map(v=>`<option value="${esc(v)}" ${f.asset_type===v?"selected":""}>${esc(v||"All asset types")}</option>`).join("")}</select>
      <div class="terrain-control-row"><span>Min confidence</span><b>${Math.round(Number(f.confidence_min||0)*100)}%</b></div>
      <input type="range" min="0" max="1" step="0.05" value="${esc(f.confidence_min||0)}" data-asset-graph-filter="confidence_min">
    </div></div>
  </section>`;
}
function dataQualityDashboardHtml(){
  return `<section class="layer-preset open">
    <button class="preset-head" type="button" style="--layer-color:#fbbf24">
      <span class="layer-icon">${DATA_ICON_SVG.risk}</span><span class="preset-title">Data Quality</span><span class="preset-meta">audit</span><span class="preset-chevron">▾</span>
    </button>
    <div class="preset-body"><div class="quality-grid" id="dataQualityDashboard"><div class="story-meta">Loading evidence coverage…</div></div></div>
  </section>`;
}
function layerStatus(layer){
  if(layer.id==="relief-terrain"||layer.id==="relief-hillshade") return terrainDemStatus;
  if(layer.id?.startsWith("relief-")) return {state:"not loaded yet",count:0,error:"placeholder"};
  if(layer.layerType==="external") return {state:"base",count:0,error:""};
  return dataSourceStatus[layer.source]||{state:"not loaded",count:0,error:""};
}
async function hydrateDataQuality(){
  const host=document.getElementById("dataQualityDashboard");
  if(!host) return;
  if(dataQualityPromise) return dataQualityPromise;
  if(Date.now()-dataQualityLast<15000) return;
  assignDataQualityLast(Date.now());
  assignDataQualityPromise((async()=>{
  try{
    const [summaryRes,farmsRes,industrialRes,govRes]=await Promise.all([
      fetch("/api/data-quality/summary",{cache:"no-store"}),
      fetch("/api/data-quality/layer/farms",{cache:"no-store"}),
      fetch("/api/data-quality/layer/industrial",{cache:"no-store"}),
      fetch("/api/data-quality/layer/government",{cache:"no-store"})
    ]);
    if(!summaryRes.ok) throw new Error(summaryRes.status===404?"not implemented yet":`${summaryRes.status} ${summaryRes.statusText}`);
    const s=await summaryRes.json(),farm=(await farmsRes.json()).metrics||{},ind=(await industrialRes.json()).metrics||{},gov=(await govRes.json()).metrics||{};
    const rows=[
      ["Evidence records",s.total_evidence_records],["Assets missing location",s.assets_missing_location],["Assets missing owner",s.assets_missing_owner],["Low-confidence relationships",s.low_confidence_relationships],["Stale records",s.stale_records],["Needs review",s.records_needing_review],
      ["Farms missing acres",farm.farms_missing_acres],["Farms missing last sale",farm.farms_missing_last_sale_price],["Industrial missing project cost",ind.industrial_assets_missing_project_cost],["Data centers missing MW",ind.data_centers_missing_power_capacity],["Government missing source",gov.government_facilities_missing_source]
    ];
    host.innerHTML=rows.map(([k,v])=>`<div class="quality-row"><span>${esc(k)}</span><b>${Number(v||0).toLocaleString()}</b></div>`).join("");
  }catch(err){
    host.innerHTML=`<div class="story-meta">Data quality: ${esc(err.message||"data unavailable")}</div>`;
  }
  finally{ dataQualityPromise=null; }
  })());
  return dataQualityPromise;
}
function renderDataLayerPresets(){
  const host=document.getElementById("dataLayerPresets");
  if(!host) return;
  host.innerHTML=DATA_LAYER_PRESETS.map(preset=>{
    const active=preset.layers.filter(layer=>productPrefs.dataLayers[layer.id]).length;
    const total=preset.layers.length;
    const rows=preset.layers.map(layer=>{
      const checked=productPrefs.dataLayers[layer.id]?"checked":"";
      const disabled=layer.locked?"disabled":"";
      const status=layerStatus(layer);
      const count=layer.id==="relief-terrain"||layer.id==="relief-hillshade"?(status.count||0):(dataLayerCounts[layer.id]||0);
      const stateLabel=status.state==="ready"?"ready":(status.state==="not loaded"?"not loaded":status.state);
      const title=status.error||`${layer.label} · ${stateLabel}`;
      return `<label class="layer-row ${layer.locked?"disabled":""}" style="--layer-color:${esc(layer.color)}" title="${esc(title)}">
        <input type="checkbox" data-layer-toggle="${esc(layer.id)}" ${checked} ${disabled}>
        <span class="layer-icon">${DATA_ICON_SVG[layer.icon]||DATA_ICON_SVG.risk}</span>
        <span class="layer-name">${esc(layer.label)}</span>
        <span class="layer-count">${Number(count).toLocaleString()}</span>
        <span class="layer-state">${esc(stateLabel)}</span>
      </label>`;
    }).join("");
    const reliefControls=preset.id==="reliefs"?`<div class="terrain-controls">
      <div class="terrain-control-row"><span>Terrain exaggeration</span><b>${Number(productPrefs.engine.terrainExaggeration??1.12).toFixed(1)}x</b></div>
      <input type="range" min="0" max="3" step="0.1" value="${esc(productPrefs.engine.terrainExaggeration??1.12)}" data-terrain-exaggeration>
      <button class="terrain-action" type="button" data-action="zoom-terrain-dem">Zoom to USGS 3DEP DEM</button>
      <div class="story-meta">${terrainDemStatus.state==="loaded"?`DEM loaded · Coverage: ${esc(terrainDemStatus.coverageLabel||"northwest Georgia / eastern Alabama")} · Zoom range: z${esc(terrainDemStatus.tilejson?.minzoom??6)}-z${esc(terrainDemStatus.tilejson?.maxzoom??13)} · Source: USGS 3DEP`:"DEM status: "+esc(terrainDemStatus.state)}</div>
      <div class="relief-legend"><div class="legend-ramp"></div><div><span>low relief</span><span>steep / high relief</span></div></div>
    </div>`:"";
    const marketplaceControls=preset.id==="marketplace"?marketplaceControlsHtml():"";
    return `<section class="layer-preset ${DATA_LAYER_OPEN[preset.id]?"open":""}" data-preset="${esc(preset.id)}">
      <button class="preset-head" type="button" data-layer-preset="${esc(preset.id)}" style="--layer-color:${esc(preset.color)}">
        <span class="layer-icon">${DATA_ICON_SVG[preset.icon]||DATA_ICON_SVG.risk}</span>
        <span class="preset-title">${esc(preset.label)}</span>
        <span class="preset-meta">${active}/${total}</span>
        <span class="preset-chevron">▾</span>
      </button>
      <div class="preset-body">${reliefControls}${marketplaceControls}${rows}</div>
    </section>`;
  }).join("")+assetGraphControlsHtml()+dataQualityDashboardHtml();
  setTimeout(hydrateDataQuality,0);
}
function setDataLayer(id,on){
  if(!DATA_LAYER_BY_ID[id]) return;
  productPrefs.dataLayers[id]=!!on;
  saveProductPrefs();
  applyDueDiligenceLayerVisibility();
  renderDataLayerPresets();
  queueSaveView();
}
function updateStats(){ document.getElementById("stNodes").textContent=COMPANIES.filter(visibleNode).length.toLocaleString(); document.getElementById("stEdges").textContent=visibleEdges().length.toLocaleString(); updateDataHealth(); }
function refresh(refit=false){ invalidateVisibilityCache(); updateStats(); draw(); if(selected&&!visibleNode(byId[selected])) deselect(); if(refit&&!selected&&mode!=="globe") fit(); if(selected) select(selected); queueSaveView(); }
asOfInput.addEventListener("input",()=>{ if(Number(asOfInput.value)>CURRENT_YEAR) asOfInput.value=CURRENT_YEAR; refresh(true); });

/* ---------- search ---------- */
const searchInput=document.getElementById("search"),results=document.getElementById("results");
function searchScore(c,raw){
  const q=normText(raw),name=normText(c.n),ticker=String(c.t||"").toUpperCase(),id=String(c.id||"").toUpperCase(),rawUpper=raw.trim().toUpperCase();
  const terms=q.split(" ").filter(Boolean);
  const termHits=terms.filter(t=>name.includes(t)).length;
  let score=0;
  if(ticker===rawUpper) score+=220;
  if(id===rawUpper) score+=200;
  if(name===q) score+=190;
  if(termHits===terms.length&&terms.length) score+=120;
  score+=termHits*14;
  if(name.startsWith(q)) score+=45;
  if(name.includes(q)) score+=30;
  if(ticker.startsWith(rawUpper)) score+=55;
  if(c.country) score+=35;
  if(c.exchange) score+=12;
  if(c.id.includes(":")) score+=10;
  if(c.kind==="public") score+=6;
  if(EXCHANGE_HQ_VALUES.has(String(c.hq||""))) score-=60;
  return score;
}
searchInput.addEventListener("input",()=>{ const q=searchInput.value.toLowerCase().trim(); if(!q){ results.classList.remove("show"); return; }
  const raw=searchInput.value.trim(),seen=new Set(),m=[];
  const add=c=>{ if(c&&existsInYear(c)&&!seen.has(c.id)){ seen.add(c.id); m.push(c); } };
  add(byId[ALIASES[raw]]);
  Object.entries(ALIASES).forEach(([a,id])=>{ if(a.toLowerCase().includes(q)) add(byId[id]); });
  COMPANIES.forEach(c=>{ if(m.length<40&&existsInYear(c)&&(c.n.toLowerCase().includes(q)||c.t.toLowerCase().includes(q)||c.id.toLowerCase().includes(q))) add(c); });
  m.sort((a,b)=>searchScore(b,raw)-searchScore(a,raw)||a.n.localeCompare(b.n));
  m.length= Math.min(m.length,8);
  results.innerHTML=m.map(c=>`<div data-pick-id="${esc(c.id)}"><span>${esc(c.n)}</span><span style="color:var(--text-3)">${esc(c.t)}</span></div>`).join(""); results.classList.toggle("show",m.length>0);
});
results.addEventListener("click",e=>{ const row=e.target.closest("[data-pick-id]"); if(row) pickSearch(row.dataset.pickId); });
window.pickSearch=async id=>{ results.classList.remove("show"); const c=byId[id]; if(!c||!existsInYear(c)) return; searchInput.value=c.n; if(mode==="globe"){ select(id); focusGlobeOn(id); return; } if(mode==="network"&&!hasVisibleEdge(c)){ await setMode("index"); } select(id); centerOn(id); };
function centerOn(id){ if(mode==="globe"){ focusGlobeOn(id); return; } const c=byId[id],r=svg.getBoundingClientRect(); k=Math.max(k,1.5); tx=r.width/2-c.x*k; ty=r.height/2-c.y*k; applyView(); }
document.addEventListener("click",e=>{ if(!e.target.closest(".search")) results.classList.remove("show"); });

// --- Command bar keyboard: Cmd/Ctrl-K or "/" focus; arrows navigate; Enter opens; Esc closes ---
function searchRows(){ return [...results.querySelectorAll("[data-pick-id]")]; }
function moveSearchActive(delta){
  const rows=searchRows(); if(!rows.length) return;
  let i=rows.findIndex(r=>r.classList.contains("active"));
  i=i<0?(delta>0?0:rows.length-1):(i+delta+rows.length)%rows.length;
  rows.forEach(r=>r.classList.remove("active"));
  rows[i].classList.add("active"); rows[i].scrollIntoView({block:"nearest"});
}
searchInput.addEventListener("keydown",e=>{
  if(e.key==="ArrowDown"){ e.preventDefault(); moveSearchActive(1); }
  else if(e.key==="ArrowUp"){ e.preventDefault(); moveSearchActive(-1); }
  else if(e.key==="Enter"){ const a=results.querySelector("[data-pick-id].active")||results.querySelector("[data-pick-id]"); if(a){ e.preventDefault(); pickSearch(a.dataset.pickId); searchInput.blur(); } }
  else if(e.key==="Escape"){ results.classList.remove("show"); searchInput.blur(); }
});
window.addEventListener("keydown",e=>{
  const el=document.activeElement, typing=/^(INPUT|TEXTAREA|SELECT)$/.test(el?.tagName||"")||el?.isContentEditable;
  if((e.key==="k"||e.key==="K")&&(e.metaKey||e.ctrlKey)){ e.preventDefault(); searchInput.focus(); searchInput.select(); return; }
  if(e.key==="/"&&!typing){ e.preventDefault(); searchInput.focus(); return; }
  if(e.key==="Escape"){
    results.classList.remove("show");
    document.querySelectorAll(".tool-panel.show").forEach(p=>p.classList.remove("show"));
    document.getElementById("workspacePanel")?.classList.remove("show");
    if(selected) deselect();
  }
});

/* ---------- mode + toolbar ---------- */
async function setMode(m){
  if(rafId){ cancelAnimationFrame(rafId); assignRafId(null); }
  await loadBulk();
  assignMode(m);
  invalidateVisibilityCache();
  clearHoverFreeze();
  document.getElementById("toolGlobeBtn")?.classList.toggle("active",m==="globe");
  document.getElementById("map").style.display=m==="globe"?"block":"none";
  svg.style.display=m==="globe"?"none":"block";
  canvas.style.display=m==="index"?"block":"none";
  gEdges.style.display=gLabels.style.display=gNodes.style.display=(m==="index"||m==="globe")?"none":"";
  if(m==="network"){
    ensureNetworkNodes();
    const conn=COMPANIES.filter(visibleNode);
    conn.forEach((c,i)=>{ const a=i/conn.length*2*Math.PI; c.x=700+Math.cos(a)*300; c.y=470+Math.sin(a)*240; });
    runPhysics();
  } else if(m==="globe"){
    COMPANIES.forEach(c=>{ c.x=c.ix; c.y=c.iy; });
    initMapGlobe(); drawGlobe(); if(map) requestAnimationFrame(()=>map.resize());
  } else {
    COMPANIES.forEach(c=>{ c.x=c.ix; c.y=c.iy; });
    draw();
  }
  updateStats(); if(m!=="globe") fit(); syncModeButton(); syncRailActive(); queueSaveView();
  if(m==="network") setTimeout(()=>{ if(mode==="network") resolveLabelCollisions(); },2600); // de-crowd once the initial physics burst settles
}
function runPhysics(){
  const conn=COMPANIES.filter(visibleNode);
  const edges=visibleEdges().map(l=>({a:byId[l.from],b:byId[l.to],rest:120-Math.min(70,l.val/4)}));
  if(!conn.length){ draw(); return; }
  let alpha=1;
  function step(){
    if(physicsPaused()){ assignRafId(requestAnimationFrame(step)); return; }
    for(let i=0;i<conn.length;i++){ const a=conn[i]; for(let j=i+1;j<conn.length;j++){ const b=conn[j]; let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy||.01,d=Math.sqrt(d2),f=14000/d2*alpha,ux=dx/d,uy=dy/d; if(!nodeAnchored(a)){ a.x+=ux*f; a.y+=uy*f; } if(!nodeAnchored(b)){ b.x-=ux*f; b.y-=uy*f; } } }
    edges.forEach(e=>{ if(e.a.deg===0||e.b.deg===0)return; let dx=e.b.x-e.a.x,dy=e.b.y-e.a.y,d=Math.hypot(dx,dy)||.01,f=(d-e.rest)*.04*alpha,ux=dx/d,uy=dy/d; if(!nodeAnchored(e.a)){e.a.x+=ux*f;e.a.y+=uy*f;} if(!nodeAnchored(e.b)){e.b.x-=ux*f;e.b.y-=uy*f;} });
    let mx=0,my=0; conn.forEach(c=>{mx+=c.x;my+=c.y;}); mx/=conn.length; my/=conn.length;
    conn.forEach(c=>{ if(!nodeAnchored(c)){ c.x+=(700-mx)*.05; c.y+=(470-my)*.05; } });
    resolveNodeCollisions(conn,dragNode,2);
    alpha*=0.992; if(alpha<0.02) alpha=0.02;
    draw(); assignRafId(requestAnimationFrame(step));
  }
  step();
}
document.getElementById("zoomIn").onclick=()=>zoomBy(1.25); document.getElementById("zoomOut").onclick=()=>zoomBy(1/1.25); document.getElementById("zoomFit").onclick=()=>mode==="globe"&&map?map.easeTo({center:[-95,28],zoom:1.45,duration:450}):fit();
function zoomBy(f){ if(mode==="globe"&&map){ map.zoomTo(map.getZoom()+(f>1?1:-1),{duration:220}); return; } const r=svg.getBoundingClientRect(),cx=r.width/2,cy=r.height/2,nk=Math.max(.08,Math.min(7,k*f)); tx=cx-(nk/k)*(cx-tx); ty=cy-(nk/k)*(cy-ty); k=nk; applyView(); }
window.addEventListener("resize",()=>{ if(mode==="globe"){ if(map) map.resize(); else drawGlobe(); } else if(!selected) fit(); else if(mode==="index") drawCanvas(); });

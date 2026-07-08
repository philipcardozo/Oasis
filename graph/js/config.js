// Static configuration & reference data — pure, no shared state, no DOM.
export const kindMeta={
  public:{name:"Public",color:"#5aa2ff"},
  security:{name:"Security",color:"#f0b341"},
  private:{name:"Private",color:"#d9dde5"},
  government:{name:"Government",color:"#58c7f3"},
  legacy:{name:"Historical",color:"#c6a15b"},
};
export const EMPTY_GEOJSON={type:"FeatureCollection",features:[]};
export const DUE_DILIGENCE_SOURCES=[
  "relief_features",
  "industrial_assets",
  "farm_parcels",
  "government_facilities",
  "public_cameras",
  "weather_overlays",
  "infrastructure_lines",
  "marketplace_listings"
];
export const DUE_DILIGENCE_ENDPOINTS={
  relief_features:"/api/map/features.geojson?layer=reliefs",
  industrial_assets:"/api/map/features.geojson?layer=industrial_assets",
  farm_parcels:"/api/map/features.geojson?layer=farm_parcels",
  government_facilities:"/api/map/features.geojson?layer=government_facilities",
  public_cameras:"/api/cameras/public.geojson",
  weather_overlays:"/api/map/features.geojson?layer=weather",
  infrastructure_lines:"/api/map/features.geojson?layer=infrastructure",
  marketplace_listings:"/api/listings/search?format=geojson"
};

export const DATA_ICON_SVG={
  factory:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 20h18"/><path d="M5 20V9l5 3V9l5 3V7h4v13"/><path d="M8 16h1M12 16h1M16 16h1"/></svg>`,
  server:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="6" rx="1.5"/><rect x="5" y="14" width="14" height="6" rx="1.5"/><path d="M8 7h.01M8 17h.01M12 7h4M12 17h4"/></svg>`,
  hydro:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16c2 0 2-1.5 4-1.5S10 16 12 16s2-1.5 4-1.5S18 16 20 16"/><path d="M5 20c2 0 2-1.5 4-1.5S11 20 13 20s2-1.5 4-1.5S19 20 21 20"/><circle cx="12" cy="8" r="4"/><path d="M12 4v8M8.5 10l7-4"/></svg>`,
  energy:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 5 14h7l-1 8 8-13h-7l1-7Z"/></svg>`,
  farm:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20c3-5 7-7 16-7"/><path d="M4 16c4-2 8-3 16-3"/><path d="M8 13c0-5 3-8 8-9 1 5-2 9-8 9Z"/><path d="M8 13c2-2 4-4 8-9"/></svg>`,
  government:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M5 9h14M6 18V9M10 18V9M14 18V9M18 18V9"/><path d="M12 3 4 7h16l-8-4Z"/></svg>`,
  terrain:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m3 20 6-12 4 7 3-5 5 10H3Z"/><path d="m9 8 1.7 3h3.1"/></svg>`,
  camera:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h4l2-3h4l2 3h4v11H4V8Z"/><circle cx="12" cy="13" r="3.2"/></svg>`,
  weather:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 18h10a4 4 0 0 0 .4-8 6 6 0 0 0-11.2 1.6A3.4 3.4 0 0 0 7 18Z"/></svg>`,
  transmission:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 5 21M12 3l7 18M8 12h8M6.5 17h11M7 7h10"/></svg>`,
  river:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5c5 0 5 4 10 4 3 0 4-1.3 6-2"/><path d="M4 12c5 0 5 4 10 4 3 0 4-1.3 6-2"/><path d="M4 19c4 0 5-2 8-2"/></svg>`,
  barn:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 21V9l8-5 8 5v12"/><path d="M8 21v-7h8v7M8 10h8M12 4v6"/></svg>`,
  soil:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8c4-2 12-2 16 0M4 13c4-2 12-2 16 0M4 18c4-2 12-2 16 0"/></svg>`,
  tag:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12V5h7l9 9-7 7-9-9Z"/><circle cx="8" cy="8" r="1"/></svg>`,
  home:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m3 11 9-8 9 8"/><path d="M5 10v11h14V10"/><path d="M10 21v-6h4v6"/></svg>`,
  storefront:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10h16l-1-5H5l-1 5Z"/><path d="M5 10v10h14V10M8 20v-6h8v6"/><path d="M4 10c1 2 3 2 4 0 1 2 3 2 4 0 1 2 3 2 4 0 1 2 3 2 4 0"/></svg>`,
  warehouse:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21V8l9-4 9 4v13"/><path d="M7 21v-8h10v8M7 13h10M9 17h6"/></svg>`,
  flag:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 22V4"/><path d="M5 4h12l-2 4 2 4H5"/><path d="M9 22h6"/></svg>`,
  permit:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3h7l3 3v15H7V3Z"/><path d="M14 3v4h4M9 12h6M9 16h5"/></svg>`,
  value:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 6.5c-.8-1-2.2-1.5-4-1.5-2.2 0-4 1.1-4 3 0 4.5 9 2.3 9 7 0 1.9-1.8 3-4.3 3-2 0-3.7-.7-4.7-2"/></svg>`,
  link:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1 0l-2 2A5 5 0 0 0 12 20.1l1.1-1.1"/></svg>`,
  risk:`<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 3 20h18L12 3Z"/><path d="M12 9v5M12 17h.01"/></svg>`
};
export function dl(id,label,icon,source,layerType="symbol",color="#94a3b8",opts={}){
  return {id,label,icon,source,layerType,color,count:0,loaded:false,...opts};
}
export const MARKETPLACE_ASSET_TYPES=[
  ["","All asset types"],["farm","Farms"],["agricultural_land","Agricultural land"],["house","Houses"],["commercial_property","Commercial"],["industrial_parcel","Industrial parcels"],["franchise_location","Franchise"],["data_center_site","Data center sites"],["warehouse","Warehouses"],["mixed_use_property","Mixed-use"]
];
export const DATA_LAYER_PRESETS=[
  {id:"reliefs",label:"Reliefs",icon:"terrain",color:"#a3e635",layers:[
    dl("relief-terrain","Terrain / relief","terrain","relief_features","fill","#a3e635",{mapLayerIds:["dd-relief-terrain"],defaultOn:false}),
    dl("relief-hillshade","Hillshade","terrain","relief_features","external","#d8dee9",{mapLayerIds:["terrain-hillshade"],defaultOn:true}),
    dl("relief-mountains","Mountains / slope","terrain","relief_features","symbol","#e2e8f0"),
    dl("relief-plateaus","Plateaus","terrain","relief_features","fill","#b6c2a1"),
    dl("relief-water","Rivers / water bodies","river","relief_features","line","#38bdf8"),
    dl("relief-vegetation","Vegetation","farm","relief_features","fill","#22c55e"),
    dl("relief-weather","Weather","weather","weather_overlays","symbol","#7dd3fc"),
    dl("relief-infrastructure","Infrastructure","transmission","infrastructure_lines","line","#cbd5e1"),
    dl("relief-crime","Crime aggregates","risk","relief_features","fill","#fb7185"),
    dl("relief-cameras","Public cameras where legally available","camera","public_cameras","symbol","#fbbf24")
  ]},
  {id:"industrial",label:"Industrial Complex",icon:"factory",color:"#f97316",layers:[
    dl("industrial-data-centers","Data centers","server","industrial_assets","symbol","#60a5fa"),
    dl("industrial-factories","Factories","factory","industrial_assets","symbol","#fb923c"),
    dl("industrial-complexes","Industrial complexes","factory","industrial_assets","fill","#fb923c"),
    dl("industrial-energy","Energy facilities","energy","industrial_assets","symbol","#facc15"),
    dl("industrial-hydro","Hydro facilities","hydro","industrial_assets","symbol","#38bdf8"),
    dl("industrial-power-plants","Power plants","energy","industrial_assets","symbol","#fde047"),
    dl("industrial-transmission","Transmission lines","transmission","infrastructure_lines","line","#facc15"),
    dl("industrial-substations","Substations where public","transmission","infrastructure_lines","symbol","#facc15"),
    dl("industrial-logistics","Roads / rail / ports","transmission","infrastructure_lines","line","#94a3b8"),
    dl("industrial-permits","Permits","permit","industrial_assets","symbol","#cbd5e1"),
    dl("industrial-project-cost","Estimated project cost","value","industrial_assets","symbol","#34d399"),
    dl("industrial-growth","Annual growth","value","industrial_assets","symbol","#22c55e"),
    dl("industrial-demand","Demand indicators","risk","industrial_assets","symbol","#f472b6"),
    dl("industrial-owner","Owner company","factory","industrial_assets","symbol","#f8fafc"),
    dl("industrial-links","Supplier / customer links","link","industrial_assets","line","#2ec9a4")
  ]},
  {id:"farms",label:"Farms",icon:"farm",color:"#22c55e",layers:[
    dl("farm-boundaries","Farm boundaries","farm","farm_parcels","line","#84cc16"),
    dl("farm-complexes","Agricultural complexes","barn","farm_parcels","symbol","#22c55e"),
    dl("farm-crop-history","Crop history","farm","farm_parcels","fill","#a3e635"),
    dl("farm-soil-quality","Soil quality","soil","farm_parcels","fill","#b45309"),
    dl("farm-vegetation","Vegetation","farm","farm_parcels","fill","#16a34a"),
    dl("farm-water-access","Water access","river","farm_parcels","line","#38bdf8"),
    dl("farm-acres","Acres","farm","farm_parcels","symbol","#bef264"),
    dl("farm-for-sale","Farms for sale","tag","farm_parcels","symbol","#fbbf24"),
    dl("farm-yield","Estimated yield","farm","farm_parcels","symbol","#4ade80"),
    dl("farm-purchase-price","Historical purchase price","value","farm_parcels","symbol","#fde68a"),
    dl("farm-current-value","Current estimated value","value","farm_parcels","symbol","#34d399"),
    dl("farm-risk","Risk score","risk","farm_parcels","symbol","#fb7185")
  ]},
  {id:"government",label:"Government",icon:"government",color:"#38bdf8",layers:[
    dl("government-facilities","Government facilities","government","government_facilities","symbol","#38bdf8"),
    dl("government-agencies","Public agencies","government","government_facilities","symbol","#7dd3fc"),
    dl("government-restricted","Military / restricted zones only when publicly mapped","risk","government_facilities","fill","#fb7185"),
    dl("government-courthouses","Courthouses","government","government_facilities","symbol","#bfdbfe"),
    dl("government-city-halls","City halls","government","government_facilities","symbol","#93c5fd"),
    dl("government-infrastructure","Public infrastructure","transmission","infrastructure_lines","line","#cbd5e1"),
    dl("government-permits","Public permits","permit","government_facilities","symbol","#f8fafc"),
    dl("government-regulatory-zones","Regulatory zones","government","government_facilities","fill","#818cf8")
  ]},
  {id:"marketplace",label:"Marketplace",icon:"tag",color:"#f59e0b",layers:[
    dl("marketplace-farms","Farms","farm","marketplace_listings","symbol","#84cc16"),
    dl("marketplace-ag-land","Agricultural land","farm","marketplace_listings","fill","#a3e635"),
    dl("marketplace-houses","Houses","home","marketplace_listings","symbol","#60a5fa"),
    dl("marketplace-commercial","Commercial properties","storefront","marketplace_listings","symbol","#f97316"),
    dl("marketplace-industrial-parcels","Industrial parcels","warehouse","marketplace_listings","fill","#fb923c"),
    dl("marketplace-franchises","Franchise locations","flag","marketplace_listings","symbol","#f472b6"),
    dl("marketplace-data-center-sites","Data center sites","server","marketplace_listings","fill","#38bdf8"),
    dl("marketplace-warehouses","Warehouses","warehouse","marketplace_listings","symbol","#fbbf24"),
    dl("marketplace-mixed-use","Mixed-use properties","storefront","marketplace_listings","symbol","#c084fc")
  ]}
];
export const DATA_LAYER_BY_ID=Object.fromEntries(DATA_LAYER_PRESETS.flatMap(p=>p.layers.map(layer=>[layer.id,layer])));
export const DATA_LAYER_OPEN=Object.fromEntries(DATA_LAYER_PRESETS.map((p,i)=>[p.id,i===0]));

export const HQ_CITY_COORDS={};
export const COUNTRY_COORDS={
  "Benin":[9.3077,2.3158],"Burkina Faso":[12.2383,-1.5616],"Cote d'Ivoire":[7.54,-5.5471],
  "Canada":[56.1304,-106.3468],"Cayman Islands":[19.3133,-81.2546],"China":[35.8617,104.1954],"Israel":[31.0461,34.8516],"Japan":[36.2048,138.2529],
  "Ghana":[7.9465,-1.0232],"Kenya":[-0.0236,37.9062],"Mali":[17.5707,-3.9962],"Morocco":[31.7917,-7.0926],"Netherlands":[52.1326,5.2913],"Niger":[17.6078,8.0817],
  "Norway":[60.472,8.4689],"Portugal":[39.3999,-8.2245],"Senegal":[14.4974,-14.4524],"South Korea":[35.9078,127.7669],"Switzerland":[46.8182,8.2275],
  "Spain":[40.4637,-3.7492],"Taiwan":[23.6978,120.9605],"Saudi Arabia":[23.8859,45.0792],"Togo":[8.6195,0.8248],"United Arab Emirates":[23.4241,53.8478],"United Kingdom":[55.3781,-3.436],"United States":[39.8283,-98.5795]
};
export const COUNTRY_CODES={AE:"United Arab Emirates",CA:"Canada",CH:"Switzerland",CN:"China",DC:"United States",ES:"Spain",IL:"Israel",PT:"Portugal",SA:"Saudi Arabia",UK:"United Kingdom",US:"United States"};
export const BAD_HQ_VALUES=new Set(["nasdaq","nyse","otc","cboe","—","-","none","null","n/a","na",""]);
export const EXCHANGE_HQ_VALUES=new Set(["NYSE","Nasdaq","OTC","CBOE","B3","BVC","BVL","BCBA"]);

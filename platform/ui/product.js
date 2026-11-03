/* Product shell. Pipeline results remain in app.js; concept profiles never reuse them. */

/* Programme profiles and evidence boundaries */
const PROFILES = [
  { id: 'mikania', name: 'Mikania micrantha', common: 'Mile-a-minute weed', category: 'Invasive plant', state: 'Reference demo', sensor: 'VNIR hyperspectral', range: '400–1,000 nm', symbol: '❧', color: '#54754a', intro: 'From a patch of green to a clear plan of action.', description: 'Explore canopy mapping, prioritised work units and repeat surveys through the Mikania reference workflow.', question: 'Where are canopy infestations, and which areas should teams inspect first?', method: 'Hyperspectral classification, spectral unmixing and specimen verification.', evidence: 'Five simulated survey scenes, real open-data leaf spectra and GBIF occurrence records.', next: 'Collect verified Hong Kong canopy spectra and validate on independent sites and seasons.' },
  { id: 'aedes', name: 'Aedes albopictus', common: 'Asian tiger mosquito', category: 'Harmful insect · habitat', state: 'Planned workstream', sensor: 'SWIR + ground inspection', range: '900–1,700 nm · proposed', symbol: '⌁', color: '#557c8b', intro: 'A clearer picture of potential breeding habitat.', description: 'Preview a standing-water inspection workflow. This profile is a development concept; survey data has not yet been collected.', question: 'Where is visible standing water that warrants a breeding-habitat inspection?', method: 'Proposed SWIR water measurements, RGB comparison and ground checks.', evidence: 'No water detector or Aedes validation dataset is implemented in this repository.', next: 'Measure water and confusing surfaces, compare with RGB and establish independent ground truth.' },
  { id: 'expansion', name: 'Additional species', common: 'Future survey profiles', category: 'Plants, animals & insects', state: 'Roadmap', sensor: 'Target-specific sensing', range: 'To be determined', symbol: '✣', color: '#997d56', intro: 'One workspace. A growing view of biodiversity.', description: 'A place for future invasive plant, animal and insect programmes, each with its own evidence and validation requirements.', question: 'Which target and survey method can support a useful management decision?', method: 'Select a sensing or field method for each species and survey setting.', evidence: 'No general animal detector or universal species classifier is implemented.', next: 'Define the target, establish observability and build verified references before a pilot.' }
];

/* Navigation and shared controls */
const NAV = [['dashboard','grid','Overview'],['maps','map','Map explorer'],['profiles','leaf','Species profiles'],['library','layers','Reference library'],['surveys','scan','Survey portfolio'],['workplan','list','Work planner'],['efficacy','trend','Change & monitoring'],['research','flask','Evidence room']];
const ICONS = {
 grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
 map:'<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3Z"/><path d="M9 3v15M15 6v15"/>',
 leaf:'<path d="M5 20C1 8 12 2 21 3c1 12-6 19-16 17Zm0 0L17 7"/>',
 layers:'<path d="m12 3 10 6-10 6L2 9Zm-10 11 10 6 10-6M2 19l10 6 10-6" transform="translate(0 -2)"/>',
 scan:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5M7 12h10M12 7v10"/>',
 list:'<path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1"/>',
 trend:'<path d="M3 3v18h18M6 16l5-6 4 3 6-8m-5 0h5v5"/>',
 flask:'<path d="M9 3h6m-5 0v7L4 20q0 1 2 1h12q2 0 2-1l-6-10V3M7 15h10"/>',
 arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
 download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
 pin:'<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
 check:'<path d="m5 12 4 4L19 6"/>',
 book:'<path d="M12 5C8 2 4 3 2 4v16c3-2 7-1 10 1 3-2 7-3 10-1V4c-2-1-6-2-10 1Zm0 0v16"/>'
};
function icon(name, cls='') { const n=el('span',{class:'icon '+cls,'aria-hidden':'true'}); n.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]||ICONS.leaf}</svg>`;return n; }
const P = { species:'mikania', librarySearch:'', libraryFilter:'all', selectedReference:'mikania', mapMode:'sites', zoom:1, pan:[0,0], selectedSite:'tai_po_kau', mapLayer:'severity', research:'overview' };
S.view='dashboard';
const profile=()=>PROFILES.find(p=>p.id===P.species)||PROFILES[0];
const isReference=()=>P.species==='mikania';
const button=(label,fn,cls='button')=>el('button',{class:cls,onclick:fn},label);
const go=view=>{location.hash=view; if(S.view===view) render();};
const pill=(text,tone='muted')=>el('span',{class:'badge '+tone},text);
const panelHead=(title,subtitle,action)=>el('div',{class:'panel-head'},el('div',{},el('h2',{},title),subtitle?el('p',{},subtitle):null),action);
function heading(kicker,title,desc,action) { return el('div',{class:'product-heading'},el('div',{},el('div',{class:'eyebrow'},kicker),el('h1',{},title),desc?el('p',{},desc):null),action); }
function toast(message) { const n=$('#toast');n.textContent=message;n.classList.add('visible');clearTimeout(toast.timer);toast.timer=setTimeout(()=>n.classList.remove('visible'),3500); }
function download(name,data,type='application/json') {const u=URL.createObjectURL(new Blob([data],{type}));const a=el('a',{href:u,download:name});a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);toast('Export ready: '+name);}
function exportSummary() {
 const p=profile(); const data={profile:p.name,status:p.state,scope:p.evidence,next_step:p.next};
 if(isReference()) Object.assign(data,{sites:S.bundle.sites.map(({spectra_grid,...s})=>s),work_plan:S.bundle.work_plan,reference_release:S.bundle.reference_database.release,notice:'Survey scenes and treatment outcomes are simulated. Not field performance.'});
 download('biomescan-'+p.id+'-summary.json',JSON.stringify(data,null,2));
}

/* Inline artwork — no remote asset dependency */
function botanical(type='mikania') {
 const n=el('div',{class:'botanical','aria-hidden':'true'});
 n.innerHTML=type==='aedes'?`<svg viewBox="0 0 400 300"><g fill="none" stroke="#b8d5da" stroke-width="2"><ellipse cx="220" cy="145" rx="8" ry="47" transform="rotate(-22 220 145)"/><path d="m210 124-80-65m88 61 54-83m-58 103-91-8m107 10 83-57m-84 77-70 72m76-70 81 35m-101-74-23-55m38 130 33 65"/><ellipse cx="183" cy="124" rx="20" ry="64" transform="rotate(-44 183 124)"/><ellipse cx="247" cy="101" rx="19" ry="61" transform="rotate(25 247 101)"/></g><g fill="none" stroke="#acc6b9" opacity=".18"><circle cx="215" cy="145" r="105"/><circle cx="215" cy="145" r="130"/></g></svg>`:`<svg viewBox="0 0 440 320"><defs><linearGradient id="leafFill" x2="1" y2="1"><stop stop-color="#c6d9a0"/><stop offset="1" stop-color="#759866"/></linearGradient></defs><g fill="none" stroke="#94b87d" stroke-width="2"><path d="M172 331C216 257 208 224 255 171S330 88 355 5"/><path d="M222 236Q155 173 91 169M251 178Q242 98 189 55M281 143Q344 151 405 114M310 97Q298 37 266 10"/></g><g fill="url(#leafFill)" stroke="#d1e1aa" stroke-width=".7"><path d="M220 238C182 244 132 222 127 177c43-14 95 6 93 61Z"/><path d="M253 180C211 155 204 105 226 74c39 10 49 66 27 106Z"/><path d="M275 153c17-47 71-61 103-42-4 43-60 65-103 42Z"/><path d="M308 102C276 77 273 42 291 19c33 12 37 53 17 83Z"/><path d="M330 68c8-36 44-53 69-46 4 33-37 53-69 46Z"/><path d="M208 272c-48 24-88 12-111-21 25-33 83-23 111 21Z"/><path d="M246 194c21-19 58-17 75 4-20 27-59 27-75-4Z"/></g><g fill="none" stroke="#3b633f" stroke-width="1.2" opacity=".7"><path d="m220 238-80-54m113-4-25-91m47 64 90-37m-57-14-15-71m37 37 59-39M208 272l-98-18m136-60 62 4"/></g><g fill="#e8e9ca"><circle cx="176" cy="109" r="3"/><circle cx="181" cy="104" r="3"/><circle cx="187" cy="108" r="3"/><circle cx="184" cy="114" r="3"/><circle cx="176" cy="116" r="3"/><circle cx="191" cy="117" r="3"/></g><path d="m181 114 52 52" stroke="#a4bb83" fill="none"/><g fill="none" stroke="#acc6b9" opacity=".13"><circle cx="270" cy="160" r="125"/><circle cx="270" cy="160" r="150"/></g></svg>`;
 return n;
}
function metric(label,value,note,ico) {return el('div',{class:'metric'},el('div',{class:'metric-top'},el('span',{},label),icon(ico)),el('div',{class:'metric-value'},value),el('div',{class:'metric-note'},note));}
function roadmapEmpty(title='This workstream starts with evidence.') {
 const p=profile();return el('div',{class:'roadmap-empty'},icon(p.id==='aedes'?'scan':'leaf'),pill(p.state,'info'),el('h2',{},title),el('p',{},p.evidence),el('div',{class:'next-step'},el('strong',{},'Next development gate'),el('p',{},p.next)),button('Explore species profile →',()=>go('profiles')));
}

/* Product views */
const PRODUCT={};
PRODUCT.dashboard=()=>{
 const p=profile(),b=S.bundle,ref=isReference();
 const wrap=el('div',{class:'dashboard'},heading('THE BIGGER PICTURE','Your biodiversity workspace.','Turn survey evidence into informed action.',button('Export summary',exportSummary,'button secondary')));
 wrap.appendChild(el('section',{class:'hero'},el('div',{class:'hero-copy'},el('div',{class:'hero-kicker'},el('span',{class:'status-dot'}),ref?'MIKANIA REFERENCE PROGRAMME':'PROGRAMME PREVIEW'),el('h2',{},p.intro),el('p',{},p.description),el('div',{class:'hero-actions'},button(ref?'Explore the map':'Explore the workflow',()=>go(ref?'maps':'profiles'),'button light'),button('Browse reference library ↗',()=>go('library'),'button hero-secondary'))),botanical(p.id),el('span',{class:'hero-specimen'},p.name+' / '+(ref?'01':'02'))));
 wrap.appendChild(el('div',{class:'metrics'},metric('Survey sites',ref?String(b.sites.length):'—',ref?'Across Hong Kong · simulated':'Awaiting a pilot dataset','pin'),metric('Mapped infestation',ref?num(b.sites.reduce((a,s)=>a+s.metrics.infested_ha,0),2)+' ha':'—',ref?'Canopy-level · simulated scenes':'No mapped observations yet','scan'),metric('Work units',ref?String(b.work_plan.length):'—',ref?'Ranked for field team review':'Inspection workflow in development','list'),metric('Reference vouchers',ref?String(b.reference_database.release.n_certified):'—',ref?'Certified in rehearsal release':'Reference collection planned','layers')));
 const mapCard=el('section',{class:'panel territory-panel'},panelHead('A landscape worth protecting',ref?'Five survey sites. One connected view.':'Hong Kong · planned survey region',button('Open map ↗',()=>go('maps'),'text-button')),territoryMap(true));
 const profileCard=el('section',{class:'panel active-profile'},panelHead('In focus','Active species profile',pill(p.state,ref?'real':'info')),el('div',{class:'specimen-art'},botanical(p.id),el('span',{class:'specimen-number'},ref?'SP.001':'SP.002')),el('div',{class:'specimen-info'},pill(p.category),el('h3',{},p.name),el('p',{},p.common),el('dl',{class:'profile-facts'},el('dt',{},'Survey method'),el('dd',{},p.sensor),el('dt',{},'Spectral range'),el('dd',{},p.range)),button('Explore species profile',()=>go('profiles'),'button secondary full')));
 wrap.appendChild(el('div',{class:'dashboard-mid'},mapCard,profileCard));
 wrap.appendChild(el('div',{class:'dashboard-bottom'},el('section',{class:'panel'},panelHead('Your survey portfolio','Explore the latest demonstration scenes',button('View all →',()=>go('surveys'),'text-button')),ref?el('div',{class:'recent-sites'},...b.sites.slice(0,3).map((s,i)=>el('button',{class:'site-row',onclick:()=>openSite(s.key)},el('span',{class:'site-monogram'},String(i+1).padStart(2,'0')),el('span',{},el('strong',{},s.name),el('small',{},s.season_label+' · '+s.metrics.n_units+' work unit'+(s.metrics.n_units===1?'':'s'))),pill(s.role==='holdout'?'Hold-out':'Training',s.role==='holdout'?'real':'muted'),icon('arrow')))):el('div',{class:'mini-empty'},'Your first pilot survey will appear here.')),el('section',{class:'panel library-preview'},panelHead('Built on better references','Trace every result to its evidence.'),el('div',{class:'reference-stack'},icon('layers'),el('div',{},el('strong',{},ref?b.library.n_measured_spectra.toLocaleString():'—'),el('span',{},ref?'measured source spectra':'references awaiting collection'))),el('p',{},ref?'Explore spectral signatures, specimen verification and versioned reference releases.':'Each new programme needs its own verified reference collection.'),button('Open reference library →',()=>go('library'),'text-button'))));
 wrap.appendChild(el('div',{class:'evidence-footnote'},icon('flask'),ref?'Demo data, clearly defined. Survey scenes and treatment outcomes are simulated; leaf spectra, GBIF records and barcode references use real open data.':'Programme preview. No survey detections, performance results or validated reference library are available for this profile.',button('Data provenance ↗',()=>go('research'),'text-button')));
 return wrap;
};
function openSite(key) {P.selectedSite=key;S.site=key;go('maps');}
/* An offline schematic, not a basemap or a substitute for the georeferenced exports. */
function territoryMap(compact=false) {
 const ref=isReference(), map=el('div',{class:'territory-map'+(compact?' compact':'')});
 const svg=svgEl('svg',{viewBox:'0 0 800 420',role:'group','aria-label':'Schematic Hong Kong survey overview. Site markers use geographic coordinates; coastline is illustrative.'});
 svg.innerHTML=`<defs><pattern id="mapGrid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#cadbd7" stroke-width=".5"/></pattern><pattern id="landPattern" width="22" height="22" patternUnits="userSpaceOnUse"><path d="m0 12 7-4 5 2 10-6" fill="none" stroke="#c9d4bb" stroke-width=".65"/></pattern></defs><rect width="800" height="420" fill="#e6eeeb"/><rect width="800" height="420" fill="url(#mapGrid)"/><g id="map-content"><g fill="#f1f0e4" stroke="#c8d3c4" stroke-width="1.3"><path d="M40 0H800V138l-26 1-17 24-21-9-10 18-19-11-13 35-17-12-17 26-15-11-21 28-13-18-25 5-18-22-26 15-19-7-15 18-28-1-18 21-22-9-12 19-25-10-13 17-29-13-18 7-16-13-19 8-14-17-25 7-12-21-29-4-5-16-28 5-11-19-28-1-15-23-31-2-9-27-20-1-4-28-22-10Z"/><path d="m264 254 29-16 26 9 15-10 22 20 37 5 25 21-11 28-31 12-16-12-30 8-18-17-25-6-11-18Z"/><path d="m450 280 22-15 29 3 11 18 31-7 17 21-24 21-37 3-17-12-32 2-12-15Z"/><path d="m627 181 14-22 15 7 6 22-14 17-17-7Z"/><path d="m660 230 16-18 17 9-2 17-18 6Z"/></g><path d="M40 0H800V138l-26 1-17 24-21-9-10 18-19-11-13 35-17-12-17 26-15-11-21 28-13-18-25 5-18-22-26 15-19-7-15 18-28-1-18 21-22-9-12 19-25-10-13 17-29-13-18 7-16-13-19 8-14-17-25 7-12-21-29-4-5-16-28 5-11-19-28-1-15-23-31-2-9-27-20-1-4-28-22-10Z" fill="url(#landPattern)"/><g fill="none" stroke="#d7c9a8" stroke-width="2" opacity=".8"><path d="M150 24q60 46 98 81t105 44 154 20 193-91"/><path d="M319 25q-25 35 18 72t76 51l-14 66"/><path d="M490 20q-45 55-27 98t78 77"/></g><g class="map-text" fill="#829185" font-family="sans-serif" font-size="12" letter-spacing="2"><text x="267" y="45">NEW TERRITORIES</text><text x="355" y="216">KOWLOON</text><text x="456" y="300" font-size="10">HONG KONG ISLAND</text><text x="283" y="284" font-size="10">LANTAU</text><text x="606" y="315" fill="#9cadab" font-size="11">PORT SHELTER</text></g></g>`;
 const content=svg.querySelector('#map-content');
 // Fixed geographic extent: 113.87–114.42 E, 22.20–22.55 N.
 const xy=(lat,lon)=>[(lon-113.87)/.55*800,(22.55-lat)/.35*420];
 if(ref && P.mapMode==='occurrences') {
  const pts=S.bundle.occurrences.points.filter(p=>p.cls==='mikania');
  pts.forEach(p=>{const [cx,cy]=xy(p.lat,p.lon);content.appendChild(svgEl('circle',{cx,cy,r:2.5,fill:'#bd744c',opacity:.53}));});
 }
 if(ref) S.bundle.sites.forEach((s,i)=>{
  const [x,y]=xy(...s.centroid); const g=svgEl('g',{class:'site-marker',role:'button',tabindex:'0','aria-label':'Select '+s.name,transform:`translate(${x},${y})`});
  g.innerHTML=`<circle r="21" fill="#4e8267" opacity=".10"/><circle r="12" fill="${s.key===P.selectedSite?'#194f3e':'#f8faf3'}" stroke="#356950" stroke-width="1.5"/><text text-anchor="middle" y="4" fill="${s.key===P.selectedSite?'#fff':'#356950'}" font-size="10" font-weight="600">${i+1}</text><text x="${i===1?-13:17}" y="${i===1?30:4}" fill="#385548" font-size="11" font-family="sans-serif">${s.name.replace(' Country Park','').replace(' Nature Reserve','').replace(' Valley','')}</text>`;
  const select=()=>{if(compact) openSite(s.key);else{P.selectedSite=s.key;S.site=s.key;render();}};
  g.addEventListener('click',select);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});content.appendChild(g);
 });
 const applyTransform=()=>content.setAttribute('transform',`translate(${400+P.pan[0]} ${210+P.pan[1]}) scale(${compact?1:P.zoom}) translate(-400 -210)`);
 applyTransform();map.appendChild(svg);
 map.appendChild(el('span',{class:'map-region'},icon('pin'),'HONG KONG SAR'));
 map.appendChild(el('div',{class:'map-key'},el('span',{class:'status-dot'}),ref?(P.mapMode==='occurrences'?'GBIF Mikania occurrences':'Simulated survey sites'):'Planned survey region'));
 map.appendChild(el('span',{class:'map-disclaimer'},'Illustrative geography · not for navigation'));
 if(!compact){
  const controls=el('div',{class:'map-zoom'},button('+',()=>{P.zoom=Math.min(3,P.zoom+.25);applyTransform();},'icon-button'),button('−',()=>{P.zoom=Math.max(1,P.zoom-.25);if(P.zoom===1)P.pan=[0,0];applyTransform();},'icon-button'),button('⌖',()=>{P.zoom=1;P.pan=[0,0];applyTransform();},'icon-button'));
  controls.children[0].setAttribute('aria-label','Zoom in');controls.children[1].setAttribute('aria-label','Zoom out');controls.children[2].setAttribute('aria-label','Reset map');map.appendChild(controls);
  let drag=null;
  svg.addEventListener('pointerdown',e=>{if(e.target.closest('.site-marker'))return;drag=[e.clientX,e.clientY,...P.pan];svg.setPointerCapture(e.pointerId);});
  svg.addEventListener('pointermove',e=>{if(!drag)return;const r=svg.getBoundingClientRect();P.pan=[drag[2]+(e.clientX-drag[0])*800/r.width,drag[3]+(e.clientY-drag[1])*420/r.height];applyTransform();});
  svg.addEventListener('pointerup',()=>drag=null);svg.addEventListener('pointercancel',()=>drag=null);
 }
 return map;
}

/* Map explorer and scene layers */
PRODUCT.maps=()=>{
 const ref=isReference(),site=S.bundle.sites.find(s=>s.key===P.selectedSite)||S.bundle.sites[0];
 const w=el('div',{},heading('SPATIAL INTELLIGENCE','Map explorer',ref?'Move between survey sites, real occurrence context and scene-level evidence.':'Preview the survey region for this planned programme.',button('Export summary',exportSummary,'button secondary')));
 const modes=el('div',{class:'seg'},...['sites','occurrences'].map(mode=>button(mode==='sites'?'Survey sites':'Occurrence context',()=>{P.mapMode=mode;render();},P.mapMode===mode?'active':'')));
 modes.querySelectorAll('button').forEach((b,i)=>b.setAttribute('aria-pressed',String(P.mapMode===['sites','occurrences'][i])));
 w.appendChild(el('div',{class:'map-toolbar'},modes,pill(ref?'Mikania · reference demo':profile().state,ref?'real':'info')));
 w.appendChild(el('section',{class:'panel map-panel'},territoryMap(),ref?el('div',{class:'map-site-strip'},...S.bundle.sites.map((s,i)=>button(String(i+1).padStart(2,'0')+'  '+s.name.replace(' Country Park','').replace(' Nature Reserve',''),()=>{P.selectedSite=s.key;S.site=s.key;render();},'site-tab '+(s.key===site.key?'selected':'')))):null));
 if(!ref){w.appendChild(roadmapEmpty('A map begins with a validated survey.'));return w;}
 w.appendChild(el('p',{class:'map-source-note'},P.mapMode==='occurrences'?'Occurrence dots are real GBIF records for Mikania; historical presence records are not current infestation estimates.':'Site markers use repository centroids. Open the scene or download GIS files for actual survey geometry.'));
 const layerControls=el('div',{class:'seg'},...['rgb','classified','severity','change','truth'].map(k=>{const b=button({rgb:'RGB',classified:'Classification',severity:'Severity',change:'Change',truth:'Ground truth'}[k],()=>{P.mapLayer=k;render();},P.mapLayer===k?'active':'');b.setAttribute('aria-pressed',String(P.mapLayer===k));return b;}));
 const scene=el('div',{class:'scene-image'},el('img',{src:site.layers[P.mapLayer],alt:P.mapLayer+' simulated scene for '+site.name}),el('span',{class:'scene-label'},'SIMULATED · '+site.shape.join(' × ')+' PX'));
 const legends=P.mapLayer==='classified'||P.mapLayer==='truth'?S.bundle.classes.filter(c=>c.id>0).map(c=>[c.color,c.label]):P.mapLayer==='severity'?[['#5aa9ff','Monitor'],['#ffb020','Schedule'],['#ff9152','Priority'],['#ff4d6d','Urgent']]:[];
 w.appendChild(el('div',{class:'scene-layout'},el('section',{class:'panel'},panelHead(site.name,site.season_label, pill(site.role==='holdout'?'Hold-out site':'Training site',site.role==='holdout'?'real':'muted')),el('div',{class:'scene-controls'},layerControls),scene,el('div',{class:'legend scene-legend'},...legends.map(([color,label])=>el('span',{class:'item'},el('span',{class:'sw',style:'background:'+color}),label)))),el('section',{class:'panel site-detail'},panelHead('From evidence to action','Selected survey site'),el('div',{class:'site-large-stat'},num(site.metrics.infested_ha,2),el('small',{},'ha mapped infestation · simulated')),el('dl',{class:'profile-facts'},el('dt',{},'Work units'),el('dd',{},site.metrics.n_units),el('dt',{},'Priority units'),el('dd',{},site.metrics.priority_units),el('dt',{},'Ground resolution'),el('dd',{},site.geo.gsd_m+' m'),el('dt',{},'Scene footprint'),el('dd',{},'EPSG:4326')),button('Inspect pixel spectra ↗',()=>{S.site=site.key;go('survey');},'button secondary full'),el('div',{class:'download-links'},el('strong',{},'GIS deliverables'),el('a',{href:'/deliverables/'+site.key+'_units.geojson',download:''},icon('download'),'Work units · GeoJSON'),el('a',{href:'/deliverables/'+site.key+'_classified.tif',download:''},icon('download'),'Classification · GeoTIFF')),el('p',{class:'hint'},'Scene-level canopy estimates; hidden sub-canopy infestations are excluded.'))));
 return w;
};

/* Species profiles */
PRODUCT.profiles=()=>{
 const p=profile(),w=el('div',{},heading('SPECIES INTELLIGENCE','A profile for every programme.','Switch context to explore the methods, evidence and next steps for each target.'));
 w.appendChild(el('div',{class:'profile-grid'},...PROFILES.map(q=>el('button',{class:'profile-card '+(q.id===p.id?'selected':''),onclick:()=>setSpecies(q.id),'aria-pressed':String(q.id===p.id)},el('div',{class:'profile-card-top'},el('span',{class:'profile-glyph',style:'color:'+q.color},q.symbol),pill(q.state,q.id==='mikania'?'real':'info')),el('h2',{},q.name),el('p',{},q.common),el('span',{class:'profile-card-bottom'},q.category,icon(q.id===p.id?'check':'arrow'))))));
 w.appendChild(el('section',{class:'panel programme-detail'},el('div',{class:'programme-intro'},el('div',{class:'eyebrow'},'ACTIVE PROGRAMME'),el('h2',{},p.name),el('p',{},p.description),el('div',{class:'programme-tags'},pill(p.sensor),pill(p.range))),el('div',{class:'programme-steps'},...[['01','The survey question',p.question],['02','Method & observation',p.method],['03','Available evidence',p.evidence],['04','Next development gate',p.next]].map(([n,h,t])=>el('div',{class:'programme-step'},el('span',{},n),el('div',{},el('h3',{},h),el('p',{},t))))),el('div',{class:'programme-actions'},button('Open map explorer →',()=>go('maps')),button('Explore reference library',()=>go('library'),'button secondary'))));
 if(p.id==='aedes')w.appendChild(el('div',{class:'callout info'},'Habitat mapping does not detect mosquitoes, larvae or eggs, establish their abundance, or confirm species presence. Concealed containers remain outside the proposed aerial observation scope.'));
 return w;
};

/* Visual reference library */
function spectrumChart(keys,large=false){
 const b=S.bundle,c=svgChart(large?700:400,large?260:160,{t:12,r:16,b:32,l:42}),wl=b.wavelengths;
 axes(c,{xTicks:[[0,'400'],[.5,'700'],[1,'1,000']],yTicks:[[0,'0'],[.5,'0.3'],[1,'0.6']],xLabel:large?'Wavelength (nm)':'nm',yLabel:large?'Reflectance':''});
 c.s.appendChild(svgEl('rect',{x:c.x((680-400)/600),y:c.pad.t,width:c.iw*80/600,height:c.ih,fill:'#94af72',opacity:.13}));
 keys.forEach(key=>{const values=b.library.endmembers[key];if(!values)return;const col=b.classes.find(c=>c.key===key)?.color||'#98816c';c.s.appendChild(svgEl('path',{d:values.map((y,i)=>`${i?'L':'M'}${c.x((wl[i]-400)/600)},${c.y(y/.6)}`).join(' '),stroke:col,'stroke-width':2.2,fill:'none'}));});
 return c.s;
}
PRODUCT.library=()=>{
 const b=S.bundle,ref=isReference(),w=el('div',{},heading('THE REFERENCE COLLECTION','Evidence you can explore.','Spectral signatures, verification records and provenance in one connected library.',ref?button('Export spectra',()=>download('biomescan-reference-spectra.csv',['wavelength_nm,'+Object.keys(b.library.endmembers).join(','),...b.wavelengths.map((wl,i)=>wl+','+Object.values(b.library.endmembers).map(v=>v[i]).join(','))].join('\n'),'text/csv'),'button secondary'):null));
 if(!ref){w.appendChild(roadmapEmpty('Make room for a new reference collection.'));return w;}
 w.appendChild(el('div',{class:'library-stats'},el('span',{},el('strong',{},Object.keys(b.library.endmembers).length),' endmember signatures'),el('span',{},el('strong',{},b.library.n_measured_spectra.toLocaleString()),' measured source spectra'),el('span',{},el('strong',{},b.reference_database.release.n_certified),' rehearsal certified vouchers')));
 const search=el('input',{type:'search',placeholder:'Search species or reference materials…',value:P.librarySearch,'aria-label':'Search reference library'});
 const grid=el('div',{class:'reference-grid'}),count=el('span',{class:'results-count','aria-live':'polite'});
 const entries=()=>Object.keys(b.library.endmembers).filter(k=>{
 const c=b.classes.find(c=>c.key===k);return ((c?.label||k).toLowerCase().includes(P.librarySearch.toLowerCase())||k.includes(P.librarySearch.toLowerCase()))&&(P.libraryFilter==='all'||(P.libraryFilter==='vegetation'?!['npv','soil_rock','shadow'].includes(k):['npv','soil_rock','shadow'].includes(k)));});
 const draw=()=>{const rows=entries();count.textContent=rows.length+' reference'+(rows.length===1?'':'s');grid.replaceChildren(...rows.map(key=>{const c=b.classes.find(c=>c.key===key),name=c?.label||'Non-photosynthetic vegetation';return el('button',{class:'reference-card '+(P.selectedReference===key?'selected':''),onclick:()=>{P.selectedReference=key;render();},'aria-pressed':String(P.selectedReference===key)},el('div',{class:'reference-card-head'},el('span',{class:'reference-dot',style:'background:'+(c?.color||'#98816c')}),pill(['npv','soil_rock','shadow'].includes(key)?'Modelled':'Hybrid reference','muted')),el('h3',{},name),el('p',{},key==='mikania'?'Target species':c?.group==='native_climber'?'Native comparison species':'Scene reference material'),spectrumChart([key]),el('div',{class:'reference-card-footer'},'121 spectral bands',el('span',{},'Inspect ↗')));}));if(!rows.length)grid.appendChild(el('div',{class:'no-results'},'No references match your search.',button('Clear filters',()=>{P.librarySearch='';P.libraryFilter='all';render();},'text-button')));};
 search.addEventListener('input',e=>{P.librarySearch=e.target.value;draw();});
 const filter=el('select',{'aria-label':'Filter reference type',onchange:e=>{P.libraryFilter=e.target.value;draw();}},...Object.entries({all:'All reference types',vegetation:'Vegetation',background:'Background materials'}).map(([value,label])=>el('option',{value,selected:P.libraryFilter===value},label)));
 w.appendChild(el('div',{class:'library-toolbar'},el('label',{class:'search-box'},icon('search'),search),filter,count));
 const selected=P.selectedReference,meta=b.classes.find(c=>c.key===selected),name=meta?.label||'Non-photosynthetic vegetation';
 w.appendChild(el('section',{class:'panel reference-inspector'},el('div',{class:'inspector-copy'},el('div',{class:'eyebrow'},'REFERENCE INSPECTOR'),el('h2',{},name),pill(selected==='mikania'?'Target signature':'Comparison signature'),el('p',{},b.library.provenance[selected]),el('p',{class:'hint'},'Shaded region: red edge, 680–760 nm. Species signatures use modelled contrasts and are not measured Hong Kong canopy spectra.'),button('Compare all signatures ↗',()=>go('spectra'),'text-button')),el('div',{},spectrumChart([selected,'host_canopy'].filter((v,i,a)=>a.indexOf(v)===i),true),el('div',{class:'legend'},...[...new Set([selected,'host_canopy'])].map(key=>el('span',{class:'item'},el('span',{class:'sw',style:'background:'+(b.classes.find(c=>c.key===key)?.color||'#98816c')}),b.classes.find(c=>c.key===key)?.label||'Non-photosynthetic vegetation'))))));
 w.appendChild(grid);draw();
 w.appendChild(el('div',{class:'library-related'},button('Barcode verification →',()=>go('barcode'),'button secondary'),button('Reference release & integrity →',()=>go('asset'),'button secondary'),button('Data provenance →',()=>go('provenance'),'button secondary')));
 return w;
};

/* Survey portfolio */
PRODUCT.surveys=()=>{
 const w=el('div',{},heading('SURVEY PORTFOLIO','Every site tells a story.','Browse seasons, catchments and independent hold-out scenes.'));
 if(!isReference()){w.appendChild(roadmapEmpty('Your next survey programme starts here.'));return w;}
 w.appendChild(el('div',{class:'survey-grid'},...S.bundle.sites.map((s,i)=>el('section',{class:'panel survey-card'},el('button',{class:'survey-preview',onclick:()=>openSite(s.key),'aria-label':'Open '+s.name},el('img',{src:s.layers.classified,alt:'Simulated classified scene for '+s.name}),pill('Simulated scene','sim'),el('span',{},String(i+1).padStart(2,'0'))),el('div',{class:'survey-copy'},pill(s.role==='holdout'?'Independent hold-out':'Training scene',s.role==='holdout'?'real':'muted'),el('h2',{},s.name),el('p',{},s.season_label),el('div',{class:'survey-facts'},el('span',{},el('strong',{},num(s.metrics.infested_ha,2)+' ha'),'mapped infestation'),el('span',{},el('strong',{},s.metrics.n_units),'work units')),button('Explore survey →',()=>openSite(s.key),'button secondary full'))))));return w;
};

/* Field shortlist and CSV delivery */
P.plannerSite='all';P.plannerBand='all';P.plannerQuery='';P.shortlist=[];P.plannerOnly=false;
try{const saved=JSON.parse(localStorage.getItem('biomescan-shortlist')||'[]');if(Array.isArray(saved))P.shortlist=saved.filter(id=>typeof id==='string');}catch{}
const csvCell=value=>'"'+String(value??'').replaceAll('"','""')+'"';
function exportUnits(units,name='biomescan-work-plan.csv'){
 const columns=['territory_rank','unit_id','site_name','area_ha','severity','mean_coverage_fraction','band','action'];
 download(name,[columns.join(','),...units.map(u=>columns.map(k=>csvCell(u[k])).join(','))].join('\n'),'text/csv');
}
PRODUCT.workplan=()=>{
 const ref=isReference(),units=S.bundle.work_plan,w=el('div',{},heading('FIELD OPERATIONS','A clearer plan for the ground.','Review priorities, explore work units and build a local field shortlist.',ref?button('Export work plan',()=>exportUnits(units),'button secondary'):null));
 if(!ref){w.appendChild(roadmapEmpty('Priorities follow the first validated survey.'));return w;}
 w.appendChild(el('div',{class:'metrics'},...S.bundle.severity_bands.map(band=>{const selected=units.filter(u=>u.band===band.label);return metric(band.label,selected.length, num(selected.reduce((a,u)=>a+u.area_ha,0),2)+' ha · simulated units','list');})));
 const tbody=el('tbody'),resultCount=el('span',{class:'results-count','aria-live':'polite'}),shortCount=el('span',{}),shortButton=button('Export shortlist',()=>exportUnits(units.filter(u=>P.shortlist.includes(u.unit_id)),'biomescan-field-shortlist.csv'),'button secondary');
 const draw=()=>{
  const rows=units.filter(u=>(P.plannerSite==='all'||u.site===P.plannerSite)&&(P.plannerBand==='all'||u.band===P.plannerBand)&&(!P.plannerOnly||P.shortlist.includes(u.unit_id))&&(u.unit_id+' '+u.site_name).toLowerCase().includes(P.plannerQuery.toLowerCase()));
  resultCount.textContent=rows.length+' work unit'+(rows.length===1?'':'s');const shortlisted=units.filter(u=>P.shortlist.includes(u.unit_id)).length;shortCount.textContent=shortlisted+' unit'+(shortlisted===1?'':'s')+' shortlisted';shortButton.disabled=!units.some(u=>P.shortlist.includes(u.unit_id));
  tbody.replaceChildren(...rows.map(u=>{
   const check=el('input',{type:'checkbox',checked:P.shortlist.includes(u.unit_id),'aria-label':'Shortlist '+u.unit_id,onchange:e=>{P.shortlist=e.target.checked?[...P.shortlist,u.unit_id]:P.shortlist.filter(id=>id!==u.unit_id);try{localStorage.setItem('biomescan-shortlist',JSON.stringify(P.shortlist));}catch{}draw();}});
   return el('tr',{},el('td',{},check),el('td',{class:'planner-rank'},String(u.territory_rank).padStart(2,'0')),el('td',{},el('strong',{},u.unit_id),el('small',{},u.site_name)),el('td',{},num(u.area_ha,3)),el('td',{},pill(u.band,'band-'+u.band)),el('td',{},el('span',{class:'severity-bar'},el('span',{style:'width:'+u.severity*100+'%'})),el('small',{},'Score '+num(u.severity,3))),el('td',{},u.action),el('td',{},button('View map ↗',()=>openSite(u.site),'text-button')));
  }));
  if(!rows.length)tbody.appendChild(el('tr',{},el('td',{colspan:'8',class:'planner-no-results'},'No units match these filters.')));
 };
 const search=el('input',{type:'search',value:P.plannerQuery,placeholder:'Search units or sites…','aria-label':'Search work units',oninput:e=>{P.plannerQuery=e.target.value;draw();}});
 const siteFilter=el('select',{'aria-label':'Filter work units by site',onchange:e=>{P.plannerSite=e.target.value;draw();}},el('option',{value:'all'},'All survey sites'),...S.bundle.sites.map(s=>el('option',{value:s.key,selected:P.plannerSite===s.key},s.name)));
 const bandFilter=el('select',{'aria-label':'Filter by priority',onchange:e=>{P.plannerBand=e.target.value;draw();}},el('option',{value:'all'},'All priorities'),...S.bundle.severity_bands.map(b=>el('option',{value:b.label,selected:P.plannerBand===b.label},b.label)));
 w.appendChild(el('div',{class:'planner-toolbar'},el('label',{class:'search-box'},icon('search'),search),siteFilter,bandFilter));
 w.appendChild(el('section',{class:'panel'},el('div',{class:'shortlist-bar'},el('label',{},el('input',{type:'checkbox',checked:P.plannerOnly,onchange:e=>{P.plannerOnly=e.target.checked;draw();}}),'Show shortlist only'),resultCount),el('div',{class:'table-wrap'},el('table',{class:'planner-table'},el('thead',{},el('tr',{},...['Select','Rank','Work unit / site','Area (ha)','Priority','Severity','Suggested action',''].map(t=>el('th',{},t)))),tbody)),el('div',{class:'shortlist-footer'},el('div',{},shortCount,el('small',{},'Saved in this browser · demonstration planning only')),shortButton)));
 w.appendChild(el('div',{class:'callout info'},'Priorities use the pipeline’s severity × area ranking. Shortlisting is a local planning aid; it does not assign crews or schedule field work. Survey scenes and actions are simulated.'));
 draw();return w;
};

/* Simulated repeat-survey monitoring */
PRODUCT.efficacy=()=>{
 const ref=isReference(),ef=S.bundle.efficacy,w=el('div',{},heading('CHANGE & MONITORING','Return to the same place. See what changed.','Explore the repeat-survey loop and identify areas for follow-up.'));
 if(!ref){w.appendChild(roadmapEmpty('Monitoring starts with a measured baseline.'));return w;}
 const site=S.bundle.sites.find(s=>s.key===P.selectedSite)||S.bundle.sites[0],outcome=ef.per_site.find(s=>s.site===site.key);
 w.appendChild(el('div',{class:'monitoring-toolbar'},el('label',{},'Survey site',el('select',{'aria-label':'Monitoring survey site',onchange:e=>{P.selectedSite=e.target.value;render();}},...S.bundle.sites.map(s=>el('option',{value:s.key,selected:s.key===site.key},s.name)))),pill(ef.reflight_interval_months+'-month simulated re-flight','sim')));
 w.appendChild(el('div',{class:'metrics'},metric('Cleared canopy',num(outcome.cleared_ha,3)+' ha','Simulated repeat-survey estimate','leaf'),metric('New / regrowth',num(outcome.emerged_ha,3)+' ha','Areas for follow-up inspection','scan'),metric('Re-emerged units',String(outcome.n_reemerged),'Of '+outcome.n_units+' work units','trend'),metric('Significant changes',String(outcome.n_significant),'Pipeline change-detection output','check')));
 w.appendChild(el('div',{class:'monitoring-scenes'},...[[site.layers.classified,'Baseline classification','Species classes · simulated baseline'],[site.layers.change,'Repeat-survey change','Change-detection layer · simulated re-flight']].map(([src,title,note])=>el('section',{class:'panel'},panelHead(title,note),el('div',{class:'scene-image'},el('img',{src,alt:title+' for '+site.name}),el('span',{class:'scene-label'},'SIMULATED EPOCH')),el('div',{class:'monitoring-caption'},site.name,pill('Simulation','sim'))))));
 const methods=Object.entries(ef.by_method||{});
 w.appendChild(el('section',{class:'panel method-comparison'},panelHead('Compare the monitoring outcomes','Treatment groups in the simulated programme'),el('div',{class:'method-grid'},...methods.map(([key,m])=>el('div',{class:'method-card'},el('h3',{},key.replaceAll('_',' ')),el('div',{class:'method-stat'},pct(m.observed_reemergence_rate,1),el('span',{},'observed re-emergence')),el('div',{class:'method-rate-bar'},el('span',{style:'width:'+m.observed_reemergence_rate*100+'%'})),el('p',{},m.n_reemerged+' of '+m.n_units+' units · '+m.mean_reduction_pct+'% mean reduction')))),el('p',{class:'monitoring-caveat'},ef.confound_note||ef.caveat),button('Inspect full efficacy evidence ↗',()=>go('efficacy-evidence'),'text-button')));
 w.appendChild(el('div',{class:'callout info'},'These outcomes come from simulated treatment and re-flights. Differences between treatment groups do not establish comparative effectiveness in the field.'));
 return w;
};
VIEWS['efficacy-evidence']=VIEWS.efficacy;


/* Scientific evidence room */
const RESEARCH=[['overview','Research overview'],['evidence','Sensor evidence'],['validation','Model validation'],['spectra','Spectral lab'],['genomics','Genomic desk study'],['barcode','Barcode verification'],['labelrisk','Label-error risk'],['asset','Reference database'],['economics','Coverage economics'],['provenance','Data provenance']];
PRODUCT.research=()=>{
 if(!isReference())return el('div',{},heading('EVIDENCE ROOM','Build the evidence first.','Each programme needs independent validation.'),roadmapEmpty());
 return el('div',{},heading('EVIDENCE ROOM','Look beneath the map.','Explore the original pipeline outputs and the limits of each result.'),el('div',{class:'research-toolbar'},el('label',{},'Evidence collection',el('select',{'aria-label':'Evidence collection',onchange:e=>{P.research=e.target.value;render();}},...RESEARCH.map(([key,label])=>el('option',{value:key,selected:key===P.research},label))))),el('div',{class:'research-content'},VIEWS[P.research]()));
};

/* Persistent context, routing and startup */
function setSpecies(id){P.species=PROFILES.some(p=>p.id===id)?id:'mikania';try{localStorage.setItem('biomescan-species',P.species);}catch{}render();}
function render(){
 const main=$('#main');if(!S.bundle)return; const p=profile();
 $('#species-select').value=p.id;$('#profile-symbol').textContent=p.symbol;$('#profile-status').textContent=p.state;$('#profile-status').className='badge '+(isReference()?'real':'info');
 const navKey=NAV.some(([key])=>key===S.view)?S.view:['survey'].includes(S.view)?'maps':'research';
 $('#page-label').textContent=NAV.find(([key])=>key===navKey)?.[2]||'Overview';
 document.querySelectorAll('#nav button').forEach(b=>b.setAttribute('aria-current',b.dataset.view===navKey?'page':'false'));
 try{
 if(!isReference()&&!PRODUCT[S.view]) main.replaceChildren(heading('PROGRAMME PREVIEW',p.name,'An evidence-led approach to a new survey workstream.'),roadmapEmpty());
 else if(PRODUCT[S.view])main.replaceChildren(PRODUCT[S.view]());
 else main.replaceChildren(el('div',{class:'legacy-back'},button('← Back to '+(S.view==='survey'?'map explorer':'evidence room'),()=>go(S.view==='survey'?'maps':'research'),'text-button')),VIEWS[S.view]());
 }catch(error){console.error(error);main.replaceChildren(el('div',{class:'panel error-state'},el('h1',{},'This view could not be opened.'),el('p',{},'Try reopening the workspace. Your pipeline outputs are unchanged.'),button('Return to overview',()=>go('dashboard'))));}
 $('#sidebar').classList.remove('mobile-open');$('.mobile-menu').setAttribute('aria-expanded','false');
 document.title='Biomescan · '+$('#page-label').textContent;window.scrollTo(0,0);
}
$('#nav').replaceChildren(el('div',{class:'nav-label'},'EXPLORE'),...NAV.map(([key,ico,label],i)=>el('button',{'data-view':key,onclick:()=>go(key)},icon(ico),el('span',{},label),i===2?el('span',{class:'nav-count'},'3'):null)));
$('#species-select').replaceChildren(...PROFILES.map(p=>el('option',{value:p.id},p.name)));
$('#species-select').addEventListener('change',e=>setSpecies(e.target.value));
$('#profile-link').addEventListener('click',()=>go('profiles'));
$('#about-demo').addEventListener('click',()=>{if(isReference()){P.research='provenance';go('research');}else go('profiles');});
$('.mobile-menu').addEventListener('click',()=>{const open=$('#sidebar').classList.toggle('mobile-open');$('.mobile-menu').setAttribute('aria-expanded',String(open));});
window.addEventListener('hashchange',()=>{const key=location.hash.slice(1);if(key==='main')return;S.view=PRODUCT[key]||VIEWS[key]?key:'dashboard';render();});
(async()=>{try{
 const r=await fetch('data/bundle.json');if(!r.ok)throw Error('The demonstration bundle could not be loaded (HTTP '+r.status+').');S.bundle=await r.json();
 try{const saved=localStorage.getItem('biomescan-species');if(PROFILES.some(p=>p.id===saved))P.species=saved;}catch{}
 const key=location.hash.slice(1);S.view=PRODUCT[key]||VIEWS[key]?key:'dashboard';render();
 }catch(error){$('#main').replaceChildren(el('section',{class:'panel error-state'},el('h1',{},'The workspace needs its demonstration data.'),el('p',{},error.message),el('p',{},'Start the platform from the repository. If the bundle is missing, regenerate it with the platform export stage.'),button('Try again',()=>location.reload())));}})();

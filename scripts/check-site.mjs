import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { staticSecurityHeaders, headersFile } from './build-security.mjs';
const root=path.resolve('dist/client');
const posts=JSON.parse(fs.readFileSync('data/posts.json','utf8'));
const routes=['','trackers/el-nino','trackers/ai','trackers/ai/calendar','dashboards/ni-elections','dashboards/ni-electricity','dashboards/roi-electricity','dashboards/ireland-gas','blog',...posts.map(p=>'blog/'+p.slug)];
for(const route of routes){const file=route?path.join(root,route+'.html'):path.join(root,'index.html');assert.ok(fs.existsSync(file),file);const html=fs.readFileSync(file,'utf8');assert.ok(html.includes('Salmon'),`${route}: content`);assert.ok(!html.includes('Untitled site'),`${route}: title`);for(const m of html.matchAll(/(?:src|href)="(\/[^"#?]*)/g)){const target=m[1];if(target==='/'||target.startsWith('//'))continue;if(target.startsWith('/api/electricity/')){assert.ok(['/api/electricity/snapshot.json','/api/electricity/history.json'].includes(target),`Unknown electricity API link: ${target}`);continue;}if(target.startsWith('/api/gas/')){assert.equal(target,'/api/gas/manifest.json',`Unknown gas API link: ${target}`);continue;}const p=path.join(root,target);assert.ok(fs.existsSync(p)||fs.existsSync(path.join(p,'index.html'))||fs.existsSync(p.replace(/\/$/,'')+'.html'),`${route}: missing ${target}`)}console.log('OK /'+route);}
const snapshot=JSON.parse(fs.readFileSync('data/dashboard.json','utf8'));
for(const m of snapshot.metrics){assert.ok(fs.readFileSync(path.join(root,'data',m.id+'.csv'),'utf8').includes(String(m.latest.value)));}
console.log('OK source downloads');

const electricityRoot=path.join(root,'data/ni-electricity');
for(const name of ['snapshot.json','history.json','edition.json'])assert.ok(fs.existsSync(path.join(electricityRoot,name)),`Missing electricity dataset: ${name}`);
const electricityPage=fs.readFileSync(path.join(root,'dashboards/ni-electricity.html'),'utf8');
for(const content of ["Today's expected peak",'07:00 Europe/London','refresh-health','station-dialog','trend-image-png','trend-image-svg','trend-download','Open Data Licence'])assert.ok(electricityPage.includes(content),`Electricity page missing ${content}`);
assert.ok(!electricityPage.includes('auto-refresh.js'));
assert.ok(fs.readFileSync(path.join(root,'index.html'),'utf8').includes('href="/dashboards/ni-electricity/"'));
console.log('OK electricity route, navigation, downloads and live-update labels');

function htmlFiles(directory){return fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?htmlFiles(path.join(directory,entry.name)):entry.name.endsWith('.html')?[path.join(directory,entry.name)]:[]);}
const pages=htmlFiles(root).map(file=>fs.readFileSync(file,'utf8'));
assert.equal(fs.readFileSync(path.join(root,'_headers'),'utf8'),headersFile(staticSecurityHeaders(pages)),'Security headers must match every generated HTML page, including 404.');
console.log('OK strict CSP hashes and Cloudflare security headers');

const roiPage=fs.readFileSync(path.join(root,'dashboards/roi-electricity.html'),'utf8');
for(const name of ['snapshot.json','history.json']) assert.ok(fs.existsSync(path.join(root,'data/roi-electricity',name)));
for(const content of ['Republic of Ireland electricity','refresh-health','station-dialog','Greenlink','history-coverage-rows']) assert.ok(roiPage.includes(content),`ROI page missing ${content}`);
assert.ok(fs.readFileSync(path.join(root,'index.html'),'utf8').includes('href="/dashboards/roi-electricity/"'));
const roiHistory=JSON.parse(fs.readFileSync(path.join(root,'data/roi-electricity/history.json')));
assert.equal(roiHistory.dataBasis,'public-source-history');
assert.ok(roiHistory.days.length>0);
for(const s of roiHistory.series) assert.equal(s.expected,96);
console.log('OK ROI route, navigation, accepted overview and real historical fallback');

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import electricityWorker from '../workers/electricity.mjs';
import { securityHeaders, apiSecurityHeaders } from '../workers/security-headers.mjs';
const electricityStore=process.env.ELECTRICITY_LOCAL_KV_DIR && path.resolve(process.env.ELECTRICITY_LOCAL_KV_DIR);
// Opt-in mirror for reviewing the same accepted data as the hosted preview.
const electricityPreview=process.env.ELECTRICITY_PREVIEW_API;
if(electricityPreview && new URL(electricityPreview).origin!=='https://salmon-electricity-preview.peterdonaghy.workers.dev')throw new Error('Unknown electricity preview origin.');
const root=path.resolve(import.meta.dirname,'../dist/client');
const port=Number(process.env.PORT||3100);
if(!fs.existsSync(path.join(root,'index.html')))throw new Error('Run npm run build before npm start.');
const staticHeaders=()=>Object.fromEntries(fs.readFileSync(path.join(root,'_headers'),'utf8').split('\n').filter(line=>line.startsWith('  ')).map(line=>{const at=line.indexOf(':');return [line.slice(2,at),line.slice(at+1).trim()]}));
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.rsc':'text/x-component; charset=utf-8','.csv':'text/csv; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.woff2':'font/woff2','.ico':'image/x-icon'};
http.createServer(async(req,res)=>{
 for(const [name,value] of Object.entries(securityHeaders))res.setHeader(name,value);
 if(!['GET','HEAD'].includes(req.method)){res.writeHead(405,{'Allow':'GET, HEAD'});res.end();return;}
 let pathname;try{pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname)}catch{res.writeHead(400);res.end('Bad request');return;}
 if(pathname.startsWith('/api/electricity/')){
  if(electricityPreview){
   try{
    const response=await fetch(new URL(req.url,electricityPreview),{method:req.method,headers:{'User-Agent':'Mozilla/5.0 SalmonOfDataLocalPreview'},signal:AbortSignal.timeout(20000)});
    const body=req.method==='HEAD'?undefined:Buffer.from(await response.arrayBuffer());
    res.writeHead(response.status,{...apiSecurityHeaders,...Object.fromEntries([...response.headers].filter(([key])=>['content-type','cache-control','etag','x-electricity-version','retry-after'].includes(key)))});
    res.end(body);
   }catch{res.writeHead(503,{...apiSecurityHeaders,'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify({error:'Hosted preview could not be reached.'}));}
   return;
  }
  const response=await electricityWorker.fetch(new Request(`http://localhost${req.url}`,{method:req.method,headers:req.headers}),{
   ELECTRICITY_PREVIEW:'true',
   ELECTRICITY_MODE:process.env.ELECTRICITY_LOCAL_LIVE==='true'?'local':undefined,
   ELECTRICITY_DATA:{async get(key,options){
    if(!electricityStore)return null;
    const file=path.resolve(electricityStore,key);
    if(!file.startsWith(electricityStore+path.sep)||!fs.existsSync(file))return null;
    const raw=await fs.promises.readFile(file);
    return options?.type==='json'?JSON.parse(raw):new Blob([raw]).stream();
   }}
  });
  res.writeHead(response.status,Object.fromEntries(response.headers));
  res.end(req.method==='HEAD'?undefined:Buffer.from(await response.arrayBuffer()));return;
 }
 // Local replay files keep updating after the site build as collectors archive
 // accepted readings. Only the public, allowlisted static replay paths qualify.
 if(process.env.ELECTRICITY_LOCAL_LIVE==='true' && /^\/data\/electricity-replay\/(ni|roi)\/(manifest|\d{4}-\d{2}-\d{2})\.json$/.test(pathname)){
  const file=path.resolve('public','.'+pathname);
  try{
   const body=await fs.promises.readFile(file);
   res.writeHead(200,{...staticHeaders(),'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-cache'});
   res.end(req.method==='HEAD'?undefined:body);
  }catch{res.writeHead(404);res.end();}
  return;
 }
 let file=path.resolve(root,'.'+pathname);
 if(file!==root&&!file.startsWith(root+path.sep)){res.writeHead(403);res.end('Forbidden');return;}
 try{if(fs.statSync(file).isDirectory())file=path.join(file,'index.html');}catch{}
 if(!fs.existsSync(file)){const flat=path.resolve(root,'.'+pathname.replace(/\/$/,'')+'.html');if(flat.startsWith(root+path.sep)&&fs.existsSync(flat))file=flat;}
 let status=200;
 if(!fs.existsSync(file)||!fs.statSync(file).isFile()){file=path.join(root,'404.html');status=404;if(!fs.existsSync(file)){res.writeHead(404);res.end('Page not found');return;}}
 res.writeHead(status,{...staticHeaders(),'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'no-cache'});
 if(req.method==='HEAD')res.end();else fs.createReadStream(file).pipe(res);
}).listen(port,'127.0.0.1',()=>console.log(`Salmon of Data · Local: http://127.0.0.1:${port}/`));

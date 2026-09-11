import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../dist/client');
const port=Number(process.env.PORT||3100);
if(!fs.existsSync(path.join(root,'index.html')))throw new Error('Run npm run build before npm start.');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.rsc':'text/x-component; charset=utf-8','.csv':'text/csv; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.woff2':'font/woff2','.ico':'image/x-icon'};
http.createServer((req,res)=>{
 if(!['GET','HEAD'].includes(req.method)){res.writeHead(405,{'Allow':'GET, HEAD'});res.end();return;}
 let pathname;try{pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname)}catch{res.writeHead(400);res.end('Bad request');return;}
 let file=path.resolve(root,'.'+pathname);
 if(file!==root&&!file.startsWith(root+path.sep)){res.writeHead(403);res.end('Forbidden');return;}
 try{if(fs.statSync(file).isDirectory())file=path.join(file,'index.html');}catch{}
 if(!fs.existsSync(file)){const flat=path.resolve(root,'.'+pathname.replace(/\/$/,'')+'.html');if(flat.startsWith(root+path.sep)&&fs.existsSync(flat))file=flat;}
 let status=200;
 if(!fs.existsSync(file)||!fs.statSync(file).isFile()){file=path.join(root,'404.html');status=404;if(!fs.existsSync(file)){res.writeHead(404);res.end('Page not found');return;}}
 res.writeHead(status,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'});
 if(req.method==='HEAD')res.end();else fs.createReadStream(file).pipe(res);
}).listen(port,'127.0.0.1',()=>console.log(`Salmon of Data · Local: http://127.0.0.1:${port}/`));

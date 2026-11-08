// Only /api/electricity/* invokes this Worker. Other site assets are served
// directly by Cloudflare's static asset service, without Worker requests.
import { apiSecurityHeaders } from './security-headers.mjs';
import { readElectricityPointer, publicElectricityPointer } from './electricity-state.mjs';
const prefix = '/api/electricity/';
const versionPattern = /^[a-f0-9]{24}$/;
const jsonHeaders = { ...apiSecurityHeaders, 'Content-Type': 'application/json; charset=utf-8' };

function unavailable() {
  return Response.json({ error: 'Electricity data is temporarily unavailable. Please retry.' }, {
    status: 503, headers: { ...jsonHeaders, 'Cache-Control': 'no-store', 'Retry-After': '60' },
  });
}

function forRequest(response, request, cacheStatus) {
  const headers = new Headers(response.headers);
  headers.set('X-Electricity-Cache', cacheStatus);
  if (response.status === 200 && response.headers.has('ETag') && request.headers.get('If-None-Match') === response.headers.get('ETag')) {
    return new Response(null, { status: 304, headers });
  }
  return new Response(request.method === 'HEAD' ? null : response.body, {status:response.status,headers});
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith(prefix)) return env.ASSETS.fetch(request);
    if (!['GET', 'HEAD'].includes(request.method)) return new Response(null, { status: 405, headers: { ...apiSecurityHeaders, Allow: 'GET, HEAD' } });
    const route = url.pathname.slice(prefix.length);
    const replay=route.match(/^replay\/(ni|roi)\/(manifest|\d{4}-\d{2}-\d{2})\.json$/);
    const roi = route.startsWith('roi/');
    const name = roi ? route.slice(4) : route;
    const scope = roi ? 'roi/' : '';
    if (!replay && !['manifest.json', 'snapshot.json', 'history.json'].includes(name)) return new Response(null, { status: 404, headers: apiSecurityHeaders });
    const requested = replay?.[2]==='manifest'||name === 'manifest.json' ? null : url.searchParams.get('v');
    if (requested && !versionPattern.test(requested)) return new Response(null, { status: 400, headers: apiSecurityHeaders });
    if(replay && replay[2]!=='manifest' && !requested)return new Response(null,{status:400,headers:apiSecurityHeaders});
    // Cache only these allowlisted public responses. Static assets still bypass
    // the Worker, and failures never enter the cache. Local review stays fresh.
    const cache = env.ELECTRICITY_MODE === 'local' ? null : globalThis.caches?.default;
    const cacheURL = new URL(url);
    cacheURL.search = requested ? `?v=${requested}` : '';
    const cacheKey = new Request(cacheURL, { method: 'GET' });
    if (cache) {
      try {
        const hit = await cache.match(cacheKey);
        if (hit) return forRequest(hit, request, 'HIT');
      } catch { /* A cache failure must not prevent a normal KV read. */ }
    }
    try {
      let response, cacheable = false;
      if(replay) {
        const key=`public/replay/${replay[1]}/${replay[2]}`+(requested?`/${requested}`:'');
        const value=await env.ELECTRICITY_DATA.get(key,{type:'stream',cacheTtl:60});
        if(!value)return new Response(null,{status:404,headers:{...apiSecurityHeaders,'Cache-Control':'no-store'}});
        response=new Response(value,{headers:{...jsonHeaders,...(requested?{ETag:`"${requested}"`,'X-Electricity-Version':requested}:{}),'Cache-Control':requested?'public, max-age=300, s-maxage=86400, immutable':'public, max-age=30, s-maxage=60'}});
        cacheable=true;
      } else if (name === 'manifest.json') {
        const [snapshot, history] = await Promise.all(['snapshot', 'history'].map(async name => {
          const pointer = await readElectricityPointer(env.ELECTRICITY_DATA, name, scope);
          if (!pointer?.records?.length) return null;
          return { ...publicElectricityPointer(pointer), version: pointer.records[0].version };
        }));
        if (!snapshot || !roi && !history) return unavailable();
        response = Response.json({ schema: 1, enabled: true, mode: env.ELECTRICITY_MODE === 'local' ? 'local' : env.ELECTRICITY_PREVIEW === 'true' ? 'preview' : 'live', snapshot, history }, { headers: { ...jsonHeaders, 'Cache-Control': 'public, max-age=30, s-maxage=60' } });
        cacheable = true;
      } else {
        const dataset = name.slice(0, -5);
        // Pin changed-version reads to the announced version. A propagation miss
        // is retried by the browser; its current valid UI remains intact.
        const versions = requested ? [requested] : (await readElectricityPointer(env.ELECTRICITY_DATA, dataset, scope))?.records?.map(item => item.version) || [];
        for (const version of versions) {
          if (!versionPattern.test(version)) continue;
          const value = await env.ELECTRICITY_DATA.get(`public/${scope}${dataset}/${version}`, { type: 'stream', cacheTtl: 60 });
          if (!value) continue;
          const headers = { ...jsonHeaders, ETag: `"${version}"`, 'X-Electricity-Version': version,
            'Cache-Control': requested ? 'public, max-age=300, s-maxage=86400, immutable' : 'public, max-age=30, s-maxage=60' };
          response = new Response(value, { headers });
          cacheable = true;
          break;
        }
        if (!response && roi && dataset === 'history' && !requested) {
          response = Response.json({ schema: 1, dataBasis: 'unavailable', first: null, last: null, series: [], days: [] }, { headers: { ...jsonHeaders, 'Cache-Control': 'public, max-age=30' } });
        }
        if (!response) return unavailable();
      }
      if (cache && cacheable) {
        const pending = cache.put(cacheKey, response.clone()).catch(() => {});
        if (ctx?.waitUntil) ctx.waitUntil(pending);
        else await pending;
      }
      return forRequest(response, request, cache ? 'MISS' : 'BYPASS');
    } catch {
      return unavailable();
    }
  },
};

import { apiSecurityHeaders } from './security-headers.mjs';

const headers = { ...apiSecurityHeaders, 'Content-Type': 'application/json; charset=utf-8' };
const versionPattern = /^[a-f0-9]{24}$/;
const dayPattern = /^\d{4}-\d{2}-\d{2}$/;
const validDay = day => dayPattern.test(day) && !Number.isNaN(Date.parse(day)) && new Date(day).toISOString().slice(0,10) === day;
const error = status => Response.json({ error: status === 404 ? 'This gas day is unavailable.' : 'Gas data is temporarily unavailable. Please retry.' },
  { status, headers: { ...headers, 'Cache-Control': 'no-store', 'Retry-After': '60' } });

function finish(response, request) {
  const status = response.status === 200 && response.headers.has('ETag') && response.headers.get('ETag') === request.headers.get('If-None-Match') ? 304 : response.status;
  return new Response(status === 304 || request.method === 'HEAD' ? null : response.body, {status,headers:response.headers});
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (!['GET', 'HEAD'].includes(request.method)) return new Response(null, {status:405,headers:{...headers,Allow:'GET, HEAD'}});
    const manifestRequest = url.pathname === '/api/gas/manifest.json';
    const match = url.pathname.match(/^\/api\/gas\/day\/(\d{4}-\d{2}-\d{2})\.json$/);
    if (!manifestRequest && (!match || !validDay(match[1]))) return error(404);
    const version = url.searchParams.get('v');
    if (version && !versionPattern.test(version)) return error(400);
    const cache = env.GAS_MODE === 'local' ? null : globalThis.caches?.default;
    const cacheURL = new URL(url);
    cacheURL.search = !manifestRequest && version ? `?v=${version}` : '';
    const cacheKey = new Request(cacheURL, {method:'GET'});
    if (cache) {
      try { const hit = await cache.match(cacheKey); if (hit) return finish(hit, request); } catch { /* KV remains available. */ }
    }
    try {
      if (!env.GAS_DATA) return error(503);
      let response;
      if (manifestRequest) {
        const manifest = await env.GAS_DATA.get('public/gas/manifest', {type:'json',cacheTtl:60});
        if (manifest?.schema !== 1 || !Array.isArray(manifest.days) || !manifest.days.length || !validDay(manifest.latest)) return error(503);
        response = Response.json(manifest, {headers:{...headers,'Cache-Control':'public, max-age=30, s-maxage=60'}});
      } else {
        let acceptedVersion = version;
        if (!acceptedVersion) {
          const manifest = await env.GAS_DATA.get('public/gas/manifest', {type:'json',cacheTtl:60});
          acceptedVersion = manifest?.days?.find(row=>row.date === match[1])?.version;
        }
        if (!acceptedVersion || !versionPattern.test(acceptedVersion)) return error(404);
        const body = await env.GAS_DATA.get(`public/gas/day/${match[1]}/${acceptedVersion}`, {type:'stream',cacheTtl:60});
        if (!body) return error(503); // A newly published index can reach an edge first.
        response = new Response(body, {headers:{...headers,ETag:`"${acceptedVersion}"`,
          'Cache-Control':version?'public, max-age=300, s-maxage=86400, immutable':'public, max-age=30, s-maxage=60'}});
      }
      if (cache) {
        const pending = cache.put(cacheKey,response.clone()).catch(()=>{});
        if (ctx?.waitUntil) ctx.waitUntil(pending); else await pending;
      }
      return finish(response, request);
    } catch { return error(503); }
  },
};

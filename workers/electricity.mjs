// Only /api/electricity/* invokes this Worker. Other site assets are served
// directly by Cloudflare's static asset service, without Worker requests.
const prefix = '/api/electricity/';
const versionPattern = /^[a-f0-9]{24}$/;
const jsonHeaders = { 'Content-Type': 'application/json; charset=utf-8', 'X-Content-Type-Options': 'nosniff' };

function unavailable() {
  return Response.json({ error: 'Electricity data is temporarily unavailable. Please retry.' }, {
    status: 503, headers: { 'Cache-Control': 'no-store', 'Retry-After': '60' },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith(prefix)) return env.ASSETS.fetch(request);
    if (!['GET', 'HEAD'].includes(request.method)) return new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } });
    const name = url.pathname.slice(prefix.length);
    if (!['manifest.json', 'snapshot.json', 'history.json'].includes(name)) return new Response(null, { status: 404 });
    try {
      let response;
      if (name === 'manifest.json') {
        const [snapshot, history] = await Promise.all(['snapshot', 'history'].map(async name => {
          const pointer = await env.ELECTRICITY_DATA.get(`public/${name}/current`, { type: 'json', cacheTtl: 60 });
          if (!pointer?.records?.length) return null;
          return { ...pointer, version: pointer.records[0].version };
        }));
        if (!snapshot || !history) return unavailable();
        response = Response.json({ schema: 1, enabled: true, mode: env.ELECTRICITY_PREVIEW === 'true' ? 'preview' : 'live', snapshot, history }, { headers: { ...jsonHeaders, 'Cache-Control': 'public, max-age=30' } });
      } else {
        const dataset = name.slice(0, -5);
        const requested = url.searchParams.get('v');
        if (requested && !versionPattern.test(requested)) return new Response(null, { status: 400 });
        // Pin changed-version reads to the announced version. A propagation miss
        // is retried by the browser; its current valid UI remains intact.
        const versions = requested ? [requested] : (await env.ELECTRICITY_DATA.get(`public/${dataset}/current`, { type: 'json', cacheTtl: 60 }))?.records?.map(item => item.version) || [];
        for (const version of versions) {
          if (!versionPattern.test(version)) continue;
          const value = await env.ELECTRICITY_DATA.get(`public/${dataset}/${version}`, { type: 'stream', cacheTtl: 60 });
          if (!value) continue;
          const headers = { ...jsonHeaders, ETag: `"${version}"`, 'X-Electricity-Version': version,
            'Cache-Control': requested ? 'public, max-age=300' : 'public, max-age=30' };
          response = request.headers.get('If-None-Match') === headers.ETag
            ? new Response(null, { status: 304, headers }) : new Response(value, { headers });
          break;
        }
        if (!response) return unavailable();
      }
      return request.method === 'HEAD' ? new Response(null, response) : response;
    } catch {
      return unavailable();
    }
  },
};

/**
 * TBR on Libby — Cloudflare Worker CORS proxy
 *
 * Forwards /v2/libraries/{key}/media requests to thunder.api.overdrive.com
 * and adds Access-Control-Allow-Origin: * so browsers can call it.
 *
 * Deploy: paste into https://dash.cloudflare.com → Workers & Pages → Create Worker
 * or run:  wrangler deploy
 */

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // ── CORS preflight ──
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders() });
    }

    // ── Security: only proxy the OverDrive media-search path ──
    // Accepts:  /v2/libraries/{key}/media?query=...
    // Rejects everything else (no open relay).
    if (!url.pathname.startsWith('/v2/libraries/') || !url.pathname.endsWith('/media')) {
      return new Response(JSON.stringify({ error: 'not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json', ...corsHeaders() },
      });
    }

    const target = `https://thunder.api.overdrive.com${url.pathname}${url.search}`;

    let upstream;
    try {
      upstream = await fetch(target, {
        method: 'GET',
        headers: {
          'Accept':          'application/json',
          'Accept-Language': 'en-US,en;q=0.9',
          // Referer makes the request look like it originated from Libby —
          // Thunder may check this to allow the call.
          'Referer':         'https://libbyapp.com/',
          'Origin':          'https://libbyapp.com',
        },
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: 'upstream fetch failed', detail: err.message }),
        { status: 502, headers: { 'Content-Type': 'application/json', ...corsHeaders() } },
      );
    }

    const body = await upstream.arrayBuffer();

    return new Response(body, {
      status: upstream.status,
      headers: {
        'Content-Type':  upstream.headers.get('Content-Type') || 'application/json',
        'Cache-Control': 'public, max-age=120',   // 2-min edge cache cuts repeat calls
        ...corsHeaders(),
      },
    });
  },
};

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin':  '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age':       '86400',
  };
}

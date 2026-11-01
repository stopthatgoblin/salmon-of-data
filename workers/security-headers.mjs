// Also applied to static assets by scripts/build-security.mjs. Keep API errors,
// conditional responses and successful responses equally protected.
export const securityHeaders = Object.freeze({
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'no-referrer',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
  'Strict-Transport-Security': 'max-age=31536000',
});

export const apiSecurityHeaders = Object.freeze({
  ...securityHeaders,
  'Content-Security-Policy': "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
});

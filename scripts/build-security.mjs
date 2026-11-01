import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { securityHeaders } from '../workers/security-headers.mjs';

export function scriptHashes(html) {
  const hashes = [];
  for (const [, attributes, source] of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)) {
    const src = attributes.match(/\bsrc\s*=\s*(["'])(.*?)\1/i);
    if (src) {
      if (!src[2].startsWith('/') || src[2].startsWith('//') || /[\\\r\n]/.test(src[2])) {
        throw new Error('Build contains a script outside the site origin.');
      }
    } else {
      hashes.push(`'sha256-${createHash('sha256').update(source).digest('base64')}'`);
    }
  }
  return hashes;
}

export function staticSecurityHeaders(htmlPages) {
  const hashes = [...new Set(htmlPages.flatMap(scriptHashes))].sort();
  if (!hashes.length) throw new Error('No generated inline scripts found; review the site build.');
  const csp = [
    "default-src 'none'",
    `script-src 'self' ${hashes.join(' ')}`,
    // React styles, SVG charts and exported chart images need inline styles.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
  ].join('; ');
  return { ...securityHeaders, 'Content-Security-Policy': csp };
}

export function headersFile(headers) {
  const lines = ['/*', ...Object.entries(headers).map(([key, value]) => `  ${key}: ${value}`)];
  // Cloudflare rejects header lines longer than 2,000 characters. Fail the
  // build rather than silently deploy a missing or weakened policy.
  if (lines.some(line => line.length > 2000 || /[\r\n]/.test(line))) {
    throw new Error('Static security headers exceed the Cloudflare line limit.');
  }
  return lines.join('\n') + '\n';
}

export async function secureBuild(root) {
  const htmlPages = [];
  async function walk(directory) {
    for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.name === '.DS_Store' || entry.name.startsWith('._')) {
        await fs.rm(file, { recursive: true, force: true });
      } else if (entry.isSymbolicLink()) {
        throw new Error('Unexpected symlink in the public build.');
      } else if (entry.isDirectory()) {
        await walk(file);
      } else if (entry.name.endsWith('.html')) {
        htmlPages.push(await fs.readFile(file, 'utf8'));
      }
    }
  }
  await walk(root);
  const headers = staticSecurityHeaders(htmlPages);
  await fs.writeFile(path.join(root, '_headers'), headersFile(headers));
  console.log(`Security headers generated for ${htmlPages.length} HTML pages.`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await secureBuild(path.resolve('dist/client'));
}

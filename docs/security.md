# Security maintenance

The production site serves generated files through Cloudflare Static Assets.
Only `/api/electricity/*` invokes the read-only KV Worker. The separate timer
and GitHub collector hold their credentials in encrypted service secrets.
Public browser code must never receive those credentials or private collector state.

## Checks before publishing

Use the Node release pinned in `.node-version`, then run:

```sh
npm ci
npm run check
npm run build
node scripts/check-site.mjs
npm audit --audit-level=moderate
```

`npm run build` generates `dist/client/_headers` automatically. Its Content
Security Policy permits same-origin scripts and exact SHA-256 hashes of the
generated inline bootstrap scripts. It does not allow inline JavaScript in
general or `eval`. Inline styles remain necessary for React and SVG charts;
image data/blob URLs remain necessary for chart exports. The build fails if
the policy exceeds Cloudflare's 2,000-character header-line limit. Rebuild
the entire site when changing HTML or JavaScript; do not edit generated files.

Cloudflare applies `_headers` to static assets. The API applies its own
restrictive policy and security headers, including on errors and conditional
responses. Static page traffic continues to bypass the Worker.

After deployment, check response headers on the homepage, a dashboard and an
unknown URL. Exercise dashboard tabs, chart filters and PNG/SVG/CSV downloads
in a browser and check its console for CSP or hydration errors.

## Dependency updates

Dependabot checks npm packages and pinned GitHub Actions weekly. Pull requests
run the site checks with read-only repository access and no deployment secrets.
Updates require review; there is no automatic merge or deployment by Dependabot.
GitHub vulnerability alerts and Dependabot security updates are enabled, as are
secret scanning and push protection.

The `fflate` override applies the compatible security patch while Satori pins
an older release. Remove the override when the upstream dependency includes
the fix. The shadcn CLI was removed because only its stylesheet was used;
`app/shadcn-utilities.css` preserves that stylesheet and its MIT licence.

## Repository privacy

Environment files, Wrangler local secret files, private keys, local archives,
build outputs and diagnostic reports are ignored by Git. These exclusions are
additional protection, not a substitute for checking staged changes. Keep
secret scanning and push protection enabled in GitHub repository settings.

Use GitHub's noreply email address for future commits. Earlier commits retain
their original author metadata and earlier documentation; removing those
copies requires a coordinated history rewrite. No such rewrite is part of
these changes. The site's public name, biography and social links are intentional.

If a credential is ever exposed, revoke or rotate it at its provider first,
then remove the exposed copies. Cloudflare account/namespace IDs and GitHub
user IDs are public identifiers and do not grant access.

## Verification on 1 November 2026

The dependency audit fell from 32 affected package entries (including three
critical and 15 high flags) to zero known vulnerabilities. This is the result
for that lockfile and advisory database, not a promise about future advisories.
The framework, React, build tools and pinned Node runtime were updated, and
security headers and API response tests were added. Browser checks and secret
scans should be repeated when relevant code or deployment settings change.

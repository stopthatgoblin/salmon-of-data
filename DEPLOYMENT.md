# Publish Salmon of Data

This project exports a static website. Use **Cloudflare Workers Static Assets** with GitHub integration; no custom Worker script or database is required. These steps publish the current committed snapshots and Markdown posts. They do not fetch new actuals or alter the frozen forecasts.

## 1. Put the project on GitHub

Create an empty repository named `salmon-of-data` on GitHub. Do not initialize it with a README. Public is fine; remember that a public repository also exposes Markdown posts marked `draft: true`, even though the website hides them. Keep private drafts outside the repository, or choose a private repository.

In Terminal:

```sh
cd "/Volumes/External SSD/Projects/salmon-2026/el-nino-tracker"
git init -b main
git add .
git status --short
git commit -m "Launch Salmon of Data"
git remote add origin https://github.com/YOUR-USERNAME/salmon-of-data.git
git push -u origin main
```

Replace YOUR-USERNAME. Review `git status` before committing. The project's ignore file excludes dependencies, generated builds, environment files and local raw-data archives. Commit the source code, package lock, `data` JSON snapshots, `public/data`, and published Markdown posts. GitHub Desktop is an alternative to these commands: create a repository in this existing folder, commit, then Publish Repository.

## 2. Deploy with Cloudflare Workers

Use the existing `salmon-of-data` Worker connected to `stopthatgoblin/salmon-of-data`. For a new project, choose Workers & Pages → Create application, select the repository, and continue with the default Workers workflow.

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Root directory | `/` |
| Build command | `npm run build` |
| Deploy command | `npx wrangler deploy --config wrangler.static.jsonc` |
| Build variable | `NODE_VERSION` = `24.19.0` |

Commit and push `wrangler.static.jsonc` before retrying. The non-default filename avoids Vinext detecting this static export as a server-based Worker build. The explicit deploy command selects this configuration. It selects `dist/client`, serves the exported HTML routes, and prevents Wrangler's automatic framework setup. Keep the installed dependency versions and lockfile; no forced dependency upgrade is needed. The earlier log successfully built the website, then failed when automatic setup attempted a conflicting Wrangler upgrade.

The existing build token can remain if it has permission to deploy this Worker in this account; its display name does not determine its permissions. The supplied log did not show a token permission failure.

Test the assigned `*.workers.dev` address, both tracker routes, a blog post, CSV downloads and PNG downloads. Subsequent pushes to `main` rebuild and deploy automatically. Node 20.16 cannot build this project; `.node-version` pins Node 24 as well. `npm start` only serves a previously built local site.

Reference: [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/).

## 3. Connect salmonofdata.com, registered at GoDaddy

1. Add `salmonofdata.com` as a domain/zone in your Cloudflare account, selecting the Free plan if suitable. Review the imported DNS records against GoDaddy. Preserve email records (MX, SPF, DKIM and DMARC) and any other services you use.
2. Cloudflare assigns two nameservers. In GoDaddy's Domain Portfolio, select the domain → DNS → Nameservers → Change nameservers → use your own nameservers. Enter **the two names Cloudflare assigns**, then save. The registration stays at GoDaddy; Cloudflare takes over DNS. If existing DNSSEC is enabled, follow Cloudflare's migration instructions to remove the old DS record before switching, then enable DNSSEC again after activation.
3. Wait for Cloudflare to show the zone as Active. In the Worker, open **Settings → Domains & Routes → Add → Custom Domain**, enter `salmonofdata.com`, and complete the setup. Let Cloudflare create the required DNS record. Add `www.salmonofdata.com` there too.
4. Wait until both custom domains and HTTPS certificates are active. Test the home page and `https://salmonofdata.com/trackers/ai/` and `/trackers/el-nino/` directly.
5. Optionally use a Cloudflare Redirect Rule to send `www.salmonofdata.com` to the apex domain, preserving the path and query string, with a 301 status.

Use Worker custom domains so Cloudflare manages the website DNS and certificates. You do not need to buy GoDaddy hosting or transfer the domain registration.

References: [Worker custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/), [GoDaddy nameserver instructions](https://www.godaddy.com/help/change-my-domain-nameservers-664).

## 4. Redirect aidisplacementtracker.com

Do this after the new AI tracker works on the main domain. DNS alone cannot point to a URL path; use an HTTP redirect.

1. Add `aidisplacementtracker.com` to Cloudflare and change its registrar nameservers as above. If it is already managed by Cloudflare, reuse that zone.
2. Preserve email DNS records. Replace conflicting website records/bindings only when ready to retire the old site. For a redirect-only zone, create proxied (orange-cloud) A records for `@` and `www`, both pointing to `192.0.2.1`, as documented by Cloudflare. Remove the old Worker custom-domain binding if it owns these records.
3. Under **Rules → Redirect Rules**, create a Single Redirect with this custom expression:

```text
(http.host in {"aidisplacementtracker.com" "www.aidisplacementtracker.com"})
```

Use a **static** destination of `https://salmonofdata.com/trackers/ai/`, status **301**, and preserve the query string. Deploy the rule. This sends every old-domain URL to the new tracker.

If you want old deep links to retain their meaning, add these more specific rules **before** that catch-all:

- `/calendar` and `/calendar/` → `https://salmonofdata.com/#calendar`
- `/blog` and `/blog/` → `https://salmonofdata.com/blog/`
- Paths starting `/data/`: dynamic destination `concat("https://salmonofdata.com/data/ai/", substring(http.request.uri.path, 6))`. Verify any old files you need exist in the imported archive before enabling this rule.

Test both root/www hostnames over HTTPS in a private browser window. Keep the old domain registered and its redirect active so existing links continue working.

Reference: [Cloudflare redirect-only domain setup](https://developers.cloudflare.com/fundamentals/manage-domains/redirect-domain/).

## Ongoing edits

For local live edits use Node 24, then `npm run dev`. Save a file and the development server updates the page. Stop it with Ctrl+C in the terminal running it. `npm start` serves the last successful build, so it requires `npm run build` first to show edits.

For publication, save changes, commit, and push to GitHub. Cloudflare builds and publishes them. Blog posts live in `content/posts`; published posts are ordered by their frontmatter date, newest first. A draft remains hidden from the website until `draft: false` and the next build. Homepage wording is in `app/page.tsx`; tracker wording is in `components/tracker.tsx` and `components/ai-tracker.tsx`. Preserve the frozen forecast files when importing new actuals.

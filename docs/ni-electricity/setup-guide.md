# Owner setup: GitHub Actions + Workers Free + KV

Verified 1 November 2026: GitHub repository access works. The repository API confirms Actions is enabled with `allowed_actions: all`, so `actions/checkout` and `actions/setup-python` are permitted. All three repository variables and the `CLOUDFLARE_API_TOKEN` secret are present; secret values cannot be read back. The Cloudflare login and both namespace IDs have also been verified.

The owner setup below is complete. The collectors, KV adapter, Worker API, workflows and browser polling are implemented. The isolated Cloudflare preview has been seeded and tested. See the [operating guide](README.md) for validation and publication status.

## 1. Select the existing Cloudflare account

1. Open [Cloudflare](https://dash.cloudflare.com/) and sign in.
2. Select the account that already hosts `salmonofdata.com`.
3. Open **Workers & Pages** and locate the existing `salmon-of-data` Worker.
4. Confirm the account's Workers plan is **Free**. The website/domain plan and Workers plan are separate.
5. Keep this same account selected for all namespace and token steps.

## 2. Create production and preview KV namespaces

1. Open **Storage & databases → Workers KV** (it may be labelled **KV**). Cloudflare's dashboard search can find **Workers KV** if the navigation differs.
2. Select **Create a namespace**.
3. Enter `ni-electricity-prod` and create it.
4. Copy its **Namespace ID**.
5. Create a second namespace named `ni-electricity-preview` and copy that Namespace ID too.
6. Keep the two IDs labelled clearly. Use standard Workers KV.

The site configuration will bind these namespaces during implementation; no manual KV data entry is needed.

Reference: [Cloudflare KV setup](https://developers.cloudflare.com/kv/get-started/).

## 3. Copy the Cloudflare account ID

1. In the Cloudflare dashboard, press **Cmd+K** on Mac or **Ctrl+K** elsewhere.
2. Search for **Copy account ID**.
3. Select that result and retain the copied value.

Alternatively, **Workers & Pages → Account Details → Account ID** provides a copy button. Use the Account ID, not the Zone ID.

Reference: [Find account IDs](https://developers.cloudflare.com/fundamentals/account/find-account-and-zone-ids/).

## 4. Create the collector API token

1. In Cloudflare, open your profile menu and select **My Profile → API Tokens**.
2. Select **Create Token**.
3. Choose **Create Custom Token**.
4. Name it `Salmon of Data electricity collector`.
5. Add the permission **Account → Workers KV Storage → Edit**.
6. Under **Account Resources**, choose **Include → Specific account**, then select the hosting account from step 1.
7. Review the summary and create the token.
8. Copy the token value for the next step. Cloudflare only displays the full value when it is created.

Keep the token out of chat and source files. This collector token manages KV; existing Cloudflare Git integration credentials will continue deploying the website code.

Reference: [Cloudflare API tokens](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/).

## 5. Save the token as a GitHub repository secret

1. Open [stopthatgoblin/salmon-of-data](https://github.com/stopthatgoblin/salmon-of-data).
2. Select **Settings**.
3. In the sidebar, open **Secrets and variables → Actions**.
4. On the **Secrets** tab, select **New repository secret**.
5. Set **Name** to `CLOUDFLARE_API_TOKEN`.
6. Paste the Cloudflare token into **Secret**.
7. Select **Add secret**.

If a secret already exists under this name and serves another workflow, do not replace it blindly. Use a separately named collector secret and report that name so the new workflow can reference it.

Reference: [GitHub repository secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

## 6. Add three repository variables

1. Stay on **Settings → Secrets and variables → Actions**.
2. Select the **Variables** tab.
3. Select **New repository variable**.
4. Add each row below separately using **Name**, **Value**, and **Add variable**:

| Name | Value |
|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | Account ID from step 3 |
| `ELECTRICITY_KV_NAMESPACE_ID` | Namespace ID of `ni-electricity-prod` |
| `ELECTRICITY_PREVIEW_KV_NAMESPACE_ID` | Namespace ID of `ni-electricity-preview` |

These IDs are non-secret configuration. Save the actual ID values, not the namespace names. The API token belongs in Secrets, not Variables.

Reference: [GitHub repository variables](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables).

## 7. Confirm GitHub Actions is enabled

1. Open **Settings → Actions → General** in the repository.
2. Confirm Actions is enabled. With **Allow all actions and reusable workflows**, both official actions are already allowed; they do not have individual checkboxes. This repository’s API setting has been verified as `all`.
3. Existing enabled settings can remain. If using a restricted allowlist, allow those official actions; no broad permission expansion is required.
4. Leave **Workflow permissions** at **Read repository contents and packages permissions**. These data jobs publish to KV, not Git commits.

The workflow is named **NI electricity data**. Scheduled production runs start after its file reaches `main`; pushes to `codex/ni-electricity` test preview only.

Reference: [GitHub Actions repository settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository).

## 8. Confirm the existing website build connection

In **Cloudflare → Workers & Pages → salmon-of-data → Settings → Builds**, check the current Git connection. The repository documentation specifies:

| Setting | Expected value |
|---|---|
| Repository | `stopthatgoblin/salmon-of-data` |
| Production branch | `main` |
| Root directory | Repository root |
| Build command | `npm run build` |
| Deploy command | `npx wrangler deploy --config wrangler.static.jsonc` |
| Node | Read automatically from the repository’s `.node-version` file (`24.19.0`) |

There is no separate Node-version field to find. Cloudflare recognises `.node-version` in the repository root. You can leave the build dashboard unchanged. If an explicit override is ever needed, add a `NODE_VERSION` build variable under **Settings → Build → Build Variables and Secrets**. [Cloudflare build-image documentation](https://developers.cloudflare.com/workers/ci-cd/builds/build-image/).

The existing build connection was confirmed by the owner; its configuration has not been independently read through the API. The source Wrangler configuration now includes the KV binding and read API.

## 9. Handoff for implementation

After completing the settings, provide:

- Confirmation that the Workers plan is Free.
- The Cloudflare Account ID and both Namespace IDs, or confirmation that the three GitHub repository variables are populated.
- Confirmation that the collector token is saved in GitHub Secrets, including its name if different from the proposed name. Do not provide the token value.
- Any differences in the existing Cloudflare build connection.

Those account settings have now been checked. Implementation, local validation, preview seeding and collectors restored from preview KV are complete. The remaining publication steps are to verify the branch workflow using the saved GitHub secret, seed production from accepted preview state, publish the complete site through `main` and verify a production run. Existing Mac collectors remain enabled as an independent recovery source.

The [launch checklist](launch-checklist.md) contains the full parity and publication requirements.

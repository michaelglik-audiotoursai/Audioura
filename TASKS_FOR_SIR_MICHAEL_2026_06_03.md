# What Sir Michael Does — GCP Approvals + audioura.com Domain

**Date:** 2026-06-03
**Scope:** account/owner actions only (Console, DNS, domain, billing). Kiro does services; Mobile/iOS AQ do the app.
Format per item: (1) what it's called · (2) how · (3) billing · (4) your steps.

---

## PART 1 — GCP owner actions (coordinate with Kiro)

### S1 — Approve service deploys + Secret Manager
**(2)** Kiro deploys the news/newsletter/coordinates/translation services and moves the translation+coordinates OpenAI key into Secret Manager. **(3)** Cloud Run scales to zero — cents/month at test volume. **(4)** Confirm the OpenAI/AWS/R2 secrets exist (they do); approve the deploys.

### S2 — Cloud SQL lockdown
**(1)** Remove the public `0.0.0.0/0` once Kiro switches services to the native Cloud Run↔Cloud SQL connector (K8). **(3)** Free (native connector; do **not** authorize a paid VPC connector). **(4)** After Kiro confirms K8: **SQL → audioura-db → Connections → Networking →** delete the `0.0.0.0/0` authorized network (keep your own dev IP if you still want direct admin). Optionally **stop** the instance between test sessions (db-f1-micro ≈ $0 stopped).

---

## PART 2 — audioura.com domain

**Recommended hub: Cloudflare (free).** Put `audioura.com`'s DNS on Cloudflare — it gives free DNS, free **Email Routing** (forwarding), and free **Pages** static hosting, all in one place, and can front the gateway for free TLS (saving the ~$18/mo GCP load balancer). One account covers items 1–3 below.

### D1 — Official URL for the apps (Android + iPhone)
**(1)** Your public website + API host. **(2)** `www.audioura.com` = the marketing page (item D3); `api.audioura.com` = the Cloud Run gateway (Kiro's K9). App Store and Play Store listings take a **Marketing URL / Support URL** = `https://www.audioura.com`. **(3)** Domain registration ≈ $10–15/yr; DNS on Cloudflare free; TLS free. **(4)** In Cloudflare DNS: add a record for `api.audioura.com` → the gateway (Kiro gives you the target — a `*.run.app` to CNAME/proxy, or the LB IP), and a record for `www` → your Pages site. Put `https://www.audioura.com` in both store listings when you submit the apps.
> Optional later: deep-link verification files (`apple-app-site-association`, `assetlinks.json`) for universal links. Not needed for launch — note for the future.

### D2 — Email: info@ and michael.glik@ at audioura.com
**Important nuance I verified:** **receiving (forwarding) is free and easy; sending/replying *as* the custom address is the part that costs/needs setup.** Cloudflare Email Routing is **forward-only** — if you only use it, your Gmail replies go out as `audio.tours.ai@gmail.com`, **not** `info@audioura.com`. To actually reply *from* `info@audioura.com`, you need Gmail "Send mail as" backed by an SMTP server. Two paths:

- **(Recommended — simplest, fully working) Google Workspace, one user (~$7/user/month annual).**
  - `michael.glik@audioura.com` = your primary Workspace mailbox (a real work email).
  - `info@audioura.com` = a **free alias** on that same user — so one $7/mo seat covers both, and you can **Send-as** `info@` and `michael.glik@` with correct `From:`/`Reply-To:`.
  - You can either use the Workspace inbox directly, or set Gmail (`audio.tours.ai@gmail.com`) to fetch/send-as it. Full send + receive as the custom domain. **(4 steps):** sign up Google Workspace → verify `audioura.com` (add the TXT/MX records Cloudflare-side) → create user `michael.glik@` → add alias `info@` → set up Send-as.
- **(Free alternative — more fiddly) Cloudflare Email Routing + a free SMTP relay.**
  - Cloudflare Email Routing forwards `info@` and `michael.glik@` → `audio.tours.ai@gmail.com` (free, inbound only).
  - For outbound "reply as", add the address in Gmail **Settings → Accounts → Send mail as** using a free SMTP relay (e.g., Brevo's free tier) after verifying the domain. Then replies show `From: info@audioura.com`.
  - $0/month but more moving parts and sending limits.

**(3) Billing:** ~$7/user/mo (Workspace, covers both addresses on one seat) **or** $0 (Cloudflare forward + free SMTP relay). **My recommendation:** Google Workspace — it's the clean way to get exactly what you described (reply-from `info@`, plus a real `michael.glik@` work email) without juggling relays.

### D3 — Simple marketing/pointer page (awareness only — not building it)
**(1)** A one-page static site at `www.audioura.com`: app blurb + "Download on the App Store" and "Get it on Google Play" badges linking to your store listings. **(2)** Host free on **Cloudflare Pages**, **GitHub Pages**, **Netlify**, or **Vercel** — all free for a static page. The official badge art + link builders are provided by Apple ("App Store marketing guidelines / badges") and Google Play ("brand guidelines / Play badge generator"). **(3)** Free. **(4)** When ready: drop a single `index.html` into a free host and point `www` at it in Cloudflare. *(You said not to build this — noting the building blocks only: free hosts above + official store badges.)*

---

## Quick sequence for you
1. Put `audioura.com` DNS on **Cloudflare** (free hub for DNS + email forwarding + Pages).
2. Decide email: **Google Workspace ($7/mo, recommended)** for real send-as, or the free Cloudflare-forward + SMTP-relay path.
3. When Kiro gives the gateway target (K9), add `api.audioura.com` in Cloudflare DNS; the mobile app then uses `https://api.audioura.com`.
4. Put `https://www.audioura.com` as the Marketing/Support URL in the App Store + Play Store listings; host the one-page site free when you're ready.
5. After Kiro's K8, remove the Cloud SQL `0.0.0.0/0`.

---

**Sources:**
- [Cloudflare Email Routing](https://www.cloudflare.com/products/email-routing/) — free, **forward-only** (replies come from the destination, not the custom address)
- [Cloudflare Email Routing docs](https://developers.cloudflare.com/email-routing/) — no outbound/send-as
- [Google Workspace pricing](https://workspace.google.com/pricing) — Business Starter ~$7/user/mo (annual), custom domain + aliases included
- [Cloud Load Balancing pricing](https://cloud.google.com/load-balancing/pricing) — ~$18/mo if you choose the GCP LB instead of Cloudflare-fronted Cloud Run

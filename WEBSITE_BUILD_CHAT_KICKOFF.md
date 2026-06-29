# Audioura Website — Complete Build & Deploy Instruction (self-contained)

**To the chat reading this:** this single document contains everything you need — the full website copy AND the
complete privacy-policy page are embedded below. **Do not look for any other files.** Build the site from the copy
here, show it to the owner for approval, and only after they approve, help them deploy it to Cloudflare Pages.

*(Recommended model for this task: Claude Sonnet 4.6 — efficient and fully capable for a static site.)*

---

## Your mission & workflow (follow in order)
1. **Ask the owner only these 3 quick questions, then proceed:**
   - Do you have a **logo, brand colors, and app screenshots**, or should I use clean placeholders?
   - For the store buttons (apps not published yet): show **"Coming soon"** badges, or a **"Notify me at launch"** email box?
   - Confirm the public contact email is **info@audioura.com**.
2. **Build** the website as static files (spec + copy below). Single self-contained `index.html` + a `privacy.html`.
3. **Show the owner** the result: present the files and describe the layout (and, if possible, render a preview).
   **STOP here and wait for explicit approval** ("approved" / "publish it"). Do NOT deploy before that.
4. **After approval, deploy to Cloudflare Pages** and walk the owner through it step by step (steps at the bottom).
   The owner does the actual click-through (a chat can't log into their Cloudflare account).
5. Verify `https://www.audioura.com` and `https://www.audioura.com/privacy` load, and report back any remaining
   placeholders to fill (store links, Premium price, logo, screenshots).

---

## Deliverables
- **`index.html`** — one self-contained file (inline CSS; minimal/no JavaScript). Mobile-first, fast, accessible.
- **`privacy.html`** — exactly the HTML embedded in the "PRIVACY PAGE" section near the bottom of this document,
  served at `/privacy`.
- A **`site/`** folder containing both (plus any images), ready to drag into Cloudflare Pages.

## Build rules (important)
- **Consumer tone.** No investor/fundraising/development-cost content.
- **Use only the facts in this document.** Do not invent metrics, testimonials, partner names, or prices.
- Public contact email is **info@audioura.com** (never the older `info@AudioTours.AI`).
- Free-tier limits below are accurate (from the live product). The Premium **price is a placeholder**.
- Store links are **placeholders** (apps not yet published) — use the badge state the owner chose in question 2.
- No `localStorage`/backend. Keep it a plain static page.

---

## WEBSITE CONTENT (build the page from this)

### Brand
- **Name:** Audioura  (legal entity: **Audioura LLC**)
- **Tagline:** *"Audioura — Where stories guide you."*
- **Tone:** warm, effortless, hands-free, on-the-go. Theme: "listen, don't look."
- **Logo/colors/fonts:** if none provided, use a clean audio/travel palette (suggestion: deep indigo `#2b2d6e`
  with a warm amber accent `#f5a623`, large rounded sans-serif) and leave a clearly-marked slot for the real logo
  and app screenshots.

### Page structure (single scrolling landing page)
Header/nav (logo + links: What it does · Pricing · Get it · Contact) → Hero → What Audioura does → How to get it →
Pricing → Contact → Footer (with a `/privacy` link).

### SECTION 1 — Hero
- **Headline:** Where stories guide you.
- **Subhead:** Audioura turns the world around you — and the news you care about — into hands-free audio. Generate a
  walking tour of any place on earth, or listen to your newsletters and articles, all by voice.
- **CTAs:** [Download on the App Store] [Get it on Google Play] (badges; links are placeholders per question 2).
- **Visual:** app screenshot / phone mockup (placeholder if none provided).

### SECTION 2 — What Audioura does
Intro line: *One simple, voice-first app. Three ways to listen.*

**🎧 Audio Tours** — Personalized audio guidance tailored to your journey and interests. Audioura adapts in real
time for **walking, biking, driving, and virtual tours**, and works for museums, sculpture parks, and state parks,
anywhere in the world. Each point of interest comes with its history, artistic significance, and location. Navigate
entirely by voice — triple-click your headphone button to move between stops. Never look at your phone.

**📰 Audio News & Newsletters** — Go hands-free with your news. Audioura converts **any article or newsletter into
an audio stream**, reads a smart summary, and lets you decide whether to hear the full story or move on. Filter by
category (Business, Finance, Politics), by date, or by **voice search** — even advanced searches like "find
articles with X but without Y." Paste an article and its audio edition is generated instantly; drop in a newsletter
URL to get up to 10 articles.

**☕ Treats** — While you're on a tour or listening to the news, treat yourself — a coffee, lunch, or a souvenir
from nearby spots, shown right on your map.

**Voice-first, screen-free** (callout band): Start with a triple-click of your headphones or a tap of the mic, then
command: *"Play summary," "Skip," "Next article."* Compatible with most headphones. GPS gives auto directions and
POI summaries tuned to your choices. Built so you never have to look at your phone.

### SECTION 3 — How to get it
- Heading: **Get Audioura free**
- Body: Available on iPhone and Android. Download, open, and start listening.
- **Apple App Store** badge → link placeholder `<APP_STORE_URL>` (app not yet published).
- **Google Play** badge → link placeholder `<GOOGLE_PLAY_URL>` (app not yet published).
- Use the chosen badge state ("Coming soon" or "Notify me at launch" email capture).

### SECTION 4 — Pricing (Free vs Premium)
Heading: **Start free. Upgrade when you want more.** Two-column comparison. **Leave the Premium price as a placeholder.**

| | **Free** | **Premium** *(coming soon)* |
|---|---|---|
| Audio tours | 1 per day (up to 30 stops) | Up to 10 per day (up to 50 stops) |
| Audio news / newsletters | 10 per week (up to 10 min each) | 50 per week (up to 30 min each) |
| Downloads | Unlimited | Unlimited |
| Voice control | ✓ | ✓ |
| Languages / auto-translation | ✓ | ✓ |
| Treats (local offers) | ✓ | ✓ |
| Price | **$0** | `$<PRICE>/mo — placeholder` |

Footnote: "Limits help us keep the free tier sustainable. Premium pricing and availability to be announced."

### SECTION 5 — Contact
- Heading: **Let's connect**
- **Email:** info@audioura.com  ·  **Phone:** +1-617-744-9562  ·  **Social:** @letMeHear
- A simple `mailto:info@audioura.com` link is fine (keep it static).

### SECTION 6 — Footer
© 2026 Audioura LLC · [Privacy Policy](/privacy) · info@audioura.com · @letMeHear

---

## PRIVACY PAGE — save this exactly as `privacy.html` (served at /privacy)

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audioura — Privacy Policy</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         max-width: 760px; margin: 0 auto; padding: 2rem 1.25rem; line-height: 1.6; color: #1a1a1a; }
  h1 { font-size: 1.8rem; margin-bottom: .25rem; }
  h2 { font-size: 1.2rem; margin-top: 2rem; }
  .meta { color: #666; font-size: .9rem; margin-bottom: 2rem; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { border: 1px solid #ddd; padding: .55rem .7rem; text-align: left; vertical-align: top; font-size: .95rem; }
  th { background: #f5f5f7; }
  footer { margin-top: 3rem; color: #666; font-size: .85rem; }
</style>
</head>
<body>

<h1>Audioura Privacy Policy</h1>
<p class="meta">Last updated: June 11, 2026</p>

<p>Audioura ("we," "us," "our"), operated by Audioura LLC (United States), provides an AI-powered audio-tour and
audio-news mobile application (the "App"). This policy explains what information the App collects, why, and your
choices. By using Audioura you agree to this policy.</p>

<p><strong>Contact:</strong> <a href="mailto:info@audioura.com">info@audioura.com</a></p>

<h2>1. Information we collect</h2>
<table>
  <tr><th>Data</th><th>Why we collect it</th><th>Required?</th></tr>
  <tr><td>Location (precise/approximate)</td><td>To generate audio tours for places near you, place map pins for tour stops, and show relevant local offers in the Treats tab (e.g. nearby coffee shops, gas stations, gift shops).</td><td>Only when you request a location-based tour or open Treats</td></tr>
  <tr><td>Microphone audio</td><td>To accept voice input when you speak a destination or request (audio is processed to fulfill your request, not stored for advertising).</td><td>Only when you use voice input</td></tr>
  <tr><td>Device identifier</td><td>To identify your app installation, save your tours, and enforce fair-use quotas. Audioura does <strong>not</strong> require an email address or password to use the app.</td><td>Automatic</td></tr>
  <tr><td>Third-party news subscription credentials (username &amp; password)</td><td><strong>Only if you choose to connect a paid news subscription</strong> (e.g. a newspaper account), Audioura uses the credentials you enter to log in to that publisher on your behalf and retrieve the article text you asked to hear. Credentials are encrypted in transit and used solely to access content you requested.</td><td>Optional — only if you connect a subscription</td></tr>
  <tr><td>Tour content you generate</td><td>To deliver, store, and let you re-download your tours and translations.</td><td>Yes</td></tr>
  <tr><td>Device &amp; diagnostic data (crash logs, basic usage)</td><td>To diagnose crashes and improve reliability.</td><td>Automatic</td></tr>
</table>

<h2>2. How we use your information</h2>
<p>We use the data above to provide and operate the App: generating tours and news content, translating tours,
placing map pins, enforcing fair-use quotas, and fixing bugs.</p>
<p><strong>Local offers (Treats).</strong> We use your trip location to show you relevant local offers in the Treats
tab — for example coupons or deals from nearby coffee shops, gas stations, or gift shops. These offers are selected
by Audioura based on where you are; we do <strong>not</strong> give your location or identity to advertisers to do this.</p>
<p><strong>We do not sell your personal information</strong>, and we do not share it with third-party advertising
networks. We do not use your microphone audio for advertising.</p>
<p><strong>Future product improvements.</strong> In the future we may measure how long you listen to news items or
tour point-of-interest descriptions so we can better understand what interests you and improve the news articles,
summaries, and tour descriptions we generate for you. We do not do this today. If and when we introduce it, we will
update this policy and, where required, ask for your consent first.</p>

<h2>3. Third-party services</h2>
<p>As a user, you interact only with Audioura. To deliver our features, Audioura may rely on service providers that
process data <em>on our behalf and under our instructions</em> — for example cloud hosting, AI text and
text-to-speech providers used to generate and voice tours, mapping/location services, and crash-reporting tools.
You have no separate account or relationship with these providers; they act for us and may use your data only to
perform services for Audioura, not for their own purposes.</p>
<p><strong>News subscriptions you connect.</strong> If you choose to connect a paid news subscription, you authorize
Audioura to log in to that publisher on your behalf to retrieve the article text you asked to hear. In that one
case, your login is used to access <em>your own</em> subscription. Credentials are encrypted in transit.</p>

<h2>4. Data retention</h2>
<p>We keep your generated tours and device-linked data while you use the App. Voice input is processed to fulfill
your request and not retained for advertising. If you connect a news subscription, your credentials are retained
only as long as needed to access content for you and are removed when you disconnect the subscription or delete your
data. You can delete your data at any time from within the App (see Section 6).</p>

<h2>5. Children's privacy</h2>
<p>Audioura is not directed to children under 13 (or the minimum age in your country), and we do not knowingly
collect personal information from them. If you believe a child has provided us data, contact us and we will delete it.</p>

<h2>6. Your rights and choices</h2>
<p>You can withdraw microphone and location permissions at any time in your device settings (some features will stop
working). You can <strong>delete all your data</strong> (tours, any stored subscription credentials, and
device-linked records) directly in the App via <em>Settings → Delete My Data</em>, or by emailing us. Depending on
your region (e.g. GDPR, CCPA), you may have rights to access, correct, or delete your data and to request a copy;
contact us to exercise them.</p>

<h2>7. Data security</h2>
<p>We use industry-standard measures including encrypted transport (HTTPS) and access controls to protect your data.
No method of transmission or storage is completely secure, so we cannot guarantee absolute security.</p>

<h2>8. International transfers</h2>
<p>Your data may be processed on servers located outside your country (e.g. in the United States). We rely on
appropriate safeguards for such transfers where required by law.</p>

<h2>9. Changes to this policy</h2>
<p>We may update this policy from time to time. We will post the updated version here with a new "Last updated" date,
and for material changes we will provide notice in the App.</p>

<h2>10. Contact us</h2>
<p>Questions about this policy or your data: <a href="mailto:info@audioura.com">info@audioura.com</a>.</p>

<footer>© 2026 Audioura LLC. All rights reserved.</footer>

</body>
</html>
```

---

## DEPLOY — Cloudflare Pages (only after the owner approves the build)
The domain `audioura.com` is already in the owner's Cloudflare account (it currently shows a 521 because the old
origin is dead). You build the files; **the owner performs the clicks** (a chat can't log into their account). Walk
them through it:

**A) Dashboard drag-and-drop (simplest):**
1. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Upload assets** (Direct Upload).
   Project name: `audioura`.
2. Drag the `site/` folder (with `index.html` at the top level) → **Deploy**. Preview appears at `audioura.pages.dev`.
3. Project → **Custom domains** → add **`www.audioura.com`** and **`audioura.com`**. Cloudflare auto-creates the DNS
   record and SSL certificate because the domain is already on the account.
4. **Fix the 521:** delete any stale `A`/`AAAA`/`CNAME` record for `audioura.com` or `www` that points at the dead
   origin; adding the Pages custom domain replaces it.
5. Visit `https://www.audioura.com` and `/privacy` to confirm both load.

**B) Optional — auto-deploy via GitHub:** push the `site/` folder to a GitHub repo, connect it in Pages (build
command: none; output dir: `/`), then the same custom-domain step. Good if the owner wants one-click future edits.

**C) Optional — fully automated:** if the owner provides a Cloudflare **API token**, you may deploy with
`npx wrangler pages deploy ./site --project-name audioura`. Otherwise use the dashboard.

## Definition of done
- [ ] Asked the 3 setup questions; built `index.html` + `privacy.html` from the copy above.
- [ ] Showed the owner the result and **got explicit approval before deploying**.
- [ ] Deployed to Cloudflare Pages; `www.audioura.com` resolves (521 gone) and `/privacy` loads.
- [ ] Reported remaining placeholders (store links, Premium price, logo, screenshots) for the owner to fill.

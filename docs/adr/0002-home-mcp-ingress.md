# ADR-0002: Home MCP ingress — Cloudflare Tunnel + Access; Tailscale for admin only

- **Status:** Proposed. Depends on open decision #1 (domain).
- **Date:** 2026-10-08

## Context

The primary MCP server runs in an LXC on your Proxmox box, behind **CGNAT**, so you cannot open inbound ports. The seller on **Cloud Run** must reach it. Cloud Run has no `/dev/net/tun`, so a normal VPN client cannot run there.
Requirements: no inbound ports, minimal public exposure of your home, cheap, simple, and failover to Cloud Run MCP must stay possible.

## Options

| Option | How | Pros | Cons |
|--------|-----|------|------|
| **A. Cloudflare Tunnel + Access (Service Auth)** | `cloudflared` in the LXC opens outbound connections. A public hostname `mcp.<your-domain>` gets an Access policy with action **Service Auth**. The seller sends `CF-Access-Client-Id/Secret`. | Unauthenticated traffic is **blocked at Cloudflare's edge** and never reaches your house. No TUN needed (works in an unprivileged LXC). Standard, well-documented pattern. Zero Trust free plan covers up to 50 users. | Needs a domain on Cloudflare (about 10 USD/year). Cloudflare terminates TLS and sees the traffic (synthetic data: acceptable). |
| **B. Tailscale Funnel** | `tailscale funnel` exposes the MCP at `https://<node>.<tailnet>.ts.net`. | Free on all plans. No domain. You already use Tailscale. End-to-end TLS (relays don't decrypt). | **Public internet reaches your LXC**; auth is only app-level. **Beta**. Only ports 443/8443/10000. Non-configurable bandwidth limits. Tailscale in an unprivileged LXC needs TUN passthrough or userspace mode. |
| **C. Tailscale inside the Cloud Run container** | `tailscaled --tun=userspace-networking --socks5-server=localhost:1055`, ephemeral auth key, app uses `ALL_PROXY`. | **Zero public exposure** (private tailnet only). | Couples the seller image to `tailscaled`. Startup script, longer cold starts, auth-key secret, SOCKS proxying for the MCP client. More moving parts in your least-experienced area. |
| **D. Cloudflare Quick Tunnel** (`trycloudflare.com`) | One command, no account. | Zero setup. | For testing only: **no uptime guarantee, no SSE, hostname changes every run, 200 in-flight request limit**. |

## Decision

**A. Cloudflare Tunnel + Access Service Auth.** Keep **Tailscale for human/admin access** (SSH to Proxmox, reaching dev services from your laptop). This gives a clean split: Tailscale for people, Cloudflare Tunnel for service ingress.

Layers in front of the home MCP:

1. Cloudflare Access (service token) at the edge.
2. App-level `X-Haggle-Token` with scopes ([ADR-0008](0008-trusted-context-headers.md)).
3. Unprivileged LXC with an egress allow-list.

**Fallback if you don't want a domain:** option B with the same app-level token, per-token rate limiting in the MCP, and accepting that internet scanners will hit the endpoint.
**Upgrade path if you want zero exposure later:** option C.

## Why

Your threat model explicitly includes "exposure of my server". A blocks attackers before they reach your network. B lets them knock on the door and relies on your code. For a security-focused portfolio, being able to explain "edge authentication + app authentication + least-privilege container" is worth 10 USD/year.

## Consequences

- One more secret pair (CF service token) in Secret Manager. Service tokens have an expiry, so set a calendar reminder; Cloudflare emails a week before.
- The seller uses different outer auth per backend (CF headers for home, Google ID token for Cloud Run). The selector handles it ([02 §5](../02-architecture.md#5-sequence-ai-vs-ai-match-and-mcp-failover-summary)).
- Streamable HTTP responses may use SSE. Named tunnels support it (quick tunnels don't) **[verify in Week 8]**.

## Revisit if

- Cloudflare changes the free Zero Trust plan, or you drop the home MCP (cut list item 1). In that case this ADR becomes moot.

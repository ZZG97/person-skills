# Transparent proxy diagnostics

Use this sequence to avoid blaming the proxy for a client, Wi-Fi, WAN, or
destination-specific failure. Keep timestamps and distinguish current probes
from historical evidence.

## 1. Establish the client and LAN path

Inspect the default route, active interface, DHCP state, and interface errors.
On macOS, useful read-only commands include:

~~~bash
route -n get default
ipconfig getsummary en1
netstat -ibdn
~~~

Probe the router management port as well as domestic and foreign public targets.
Do not interpret a router that drops ICMP as an outage when ARP and TCP services
remain reachable.

For macOS Wi-Fi history, inspect `/var/log/wifi.log` for association loss,
deauthentication, roaming, DHCP changes, and driver faults. DHCP lease renewal
alone is not a disconnect.

## 2. Use independent long-lived witnesses

When available, inspect existing tunnel, VPN, websocket, or service logs for
reconnect intervals. One Cloudflare edge connection rotating while redundant
connections remain online is weaker evidence than all connections dropping at
the same timestamp.

Application logs can confirm impact, but do not prove cause. TLS handshake EOF,
connection reset, and stream idle timeout should be correlated with direct
network probes before changing application code or restarting the application.

## 3. Snapshot the running proxy

Locate the installed Skill root, then run:

~~~bash
skill_root=/absolute/path/to/openclash-ops
"$skill_root/scripts/openclash-api.sh" version
"$skill_root/scripts/openclash-api.sh" snapshot
~~~

Check:

- operating mode and listener ports;
- dead versus alive provider nodes;
- service selectors and nested automatic groups;
- automatic-group test URLs and currently selected nodes.

Large dead-node counts suggest provider or transport trouble, but a node marked
alive only passed its configured health URL.

## 4. Trace the affected domain

Search the ordered rule list without dumping unrelated provider configuration:

~~~bash
"$skill_root/scripts/openclash-api.sh" get /rules |
  jq --arg needle 'openai' '[
    .rules | to_entries[]
    | select((.value.payload // "") | ascii_downcase | contains($needle))
    | {index: .key, type: .value.type, payload: .value.payload, proxy: .value.proxy}
  ]'
~~~

For exact runtime evidence, issue a controlled request while sampling
`/connections`, then select records by `metadata.host`, destination fake IP, or
source IP. Record `rule`, `rulePayload`, and `chains`. Avoid closing live user
connections.

Follow nested `now` fields until the final outbound node is reached:

~~~text
domain -> matched rule -> service selector -> country/url-test group -> node
~~~

## 5. Build a service-specific node matrix

Use a neutral control URL and the failing service URL on the same candidate:

~~~bash
"$skill_root/scripts/openclash-api.sh" delay NODE \
  https://www.gstatic.com/generate_204 7000

"$skill_root/scripts/openclash-api.sh" delay NODE \
  https://api.openai.com/v1/models 7000 401
~~~

Interpretation:

| Control | Service | Likely conclusion |
|---|---|---|
| fails | fails | node or transport is generally dead |
| passes | fails | destination-specific block, TLS path, or egress-IP problem |
| passes | intermittent | unstable node, multiplexing, or upstream path |
| passes | passes | candidate is viable; repeat before selecting |

Test a proposed node 3–5 times. OpenAI `/v1/models` without credentials should
return `401`, so require that status. Without `EXPECTED_STATUS`, Mihomo may treat
any completed HTTP response as success, including an unsupported-region block.
Network reachability and product-region eligibility are separate checks; do not
put an ineligible region into a service-specific fallback group merely because
its latency probe passed.

## 6. Apply the narrowest authorized change

If a shared country URLTest group uses a generic Cloudflare health URL and picks
nodes that fail the target service, pin the outer service selector directly to a
verified node. This preserves automatic selection for unrelated traffic.

After explicit authorization:

~~~bash
"$skill_root/scripts/openclash-api.sh" select --yes 'SERVICE GROUP' 'NODE'
~~~

Do not restart the core for a selector-only problem. Verify the selection via
the API and run 5–10 real requests through the normal transparent path. Retain
the previous selector value as the rollback target.

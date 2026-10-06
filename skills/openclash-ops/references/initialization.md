# Initialization

Use this guide when installing the Skill on a new machine or connecting it to a
different OpenClash/Mihomo controller.

## Controller exposure

Configure the controller on loopback or a trusted LAN address with a strong,
unique secret. A LAN client normally needs an address such as
`http://router-lan-ip:9090`; do not add WAN port forwarding or a public tunnel.

Verify reachability before handling the secret:

~~~bash
curl -sS -o /dev/null -w '%{http_code}\n' http://router-lan-ip:9090/version
~~~

`401` is expected when the listener is reachable and authentication is enabled.

## Skill Kit values

Set these non-secret values in the repository's ignored
`skill-kit.local.json`:

~~~json
{
  "OPENCLASH_API_URL": "http://router-lan-ip:9090",
  "OPENCLASH_KEYCHAIN_SERVICE": "openclash-api",
  "OPENCLASH_KEYCHAIN_ACCOUNT": "router-lan-ip:9090",
  "OPENCLASH_SSH_HOST": "router-lan-ip",
  "OPENCLASH_SSH_USER": "root",
  "OPENCLASH_SSH_KEY_PATH": "/absolute/path/to/dedicated-private-key"
}
~~~

Never put the controller secret in that file. Run Skill Kit `validate`, `plan`,
and `apply` after resolving the values.

## Secret storage

For an ephemeral shell, set `OPENCLASH_API_SECRET` through a secure runtime
mechanism without writing it into shell history.

On macOS, store the secret in Keychain using the rendered service and account.
The interactive form keeps the value out of the command text:

~~~bash
read -s "oc_secret?OpenClash API secret: "; echo
security add-generic-password -U \
  -s '@@OPENCLASH_KEYCHAIN_SERVICE@@' \
  -a '@@OPENCLASH_KEYCHAIN_ACCOUNT@@' \
  -w "$oc_secret"
unset oc_secret
~~~

If a user pasted the secret into chat, finish the active incident and recommend
rotating it. Do not repeat it in the final report.

## Router SSH access

SSH is needed only for explicitly authorized configuration changes that the
controller API cannot perform. Generate a dedicated Ed25519 key, install only
its public half in Dropbear's `authorized_keys`, and confirm noninteractive
login before discarding the password-based session. Keep the private key local
with mode `0600`; never copy it into the Skill repository or router.

Use strict host, identity, and noninteractive options for automation:

~~~bash
ssh -i '@@OPENCLASH_SSH_KEY_PATH@@' \
  -o BatchMode=yes -o IdentitiesOnly=yes \
  '@@OPENCLASH_SSH_USER@@@@@OPENCLASH_SSH_HOST@@' 'true'
~~~

Do not store the router password. To revoke this agent's access, remove the line
whose public-key fingerprint matches the dedicated key from
`/etc/dropbear/authorized_keys`.

## Verification

Run:

~~~bash
skill_root=/absolute/path/to/openclash-ops
"$skill_root/scripts/openclash-api.sh" version
"$skill_root/scripts/openclash-api.sh" snapshot
~~~

Success means `/version` authenticates and the snapshot returns compact config,
group, and provider summaries without exposing subscription credentials.

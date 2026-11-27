# Claude desktop connector

Lets a chat in the Claude desktop app on your Mac look up your lifting from
Naradi: a day's sets, an exercise's history and your personal bests. It can't
change anything. It doesn't work in claude.ai in a browser or on a phone.

Whatever it returns becomes part of that Claude conversation.

## 1. Make a token (on the homelab)

```bash
kubectl create secret generic naradi-connector-secret --from-literal=token="$(openssl rand -hex 32)"
```

```bash
cd ~/Naradi && ./deploy.sh
```

Show the token once so you can copy it to your Mac (don't paste it into a chat):

```bash
kubectl get secret naradi-connector-secret -o jsonpath='{.data.token}' | base64 -d; echo
```

## 2. Save it in your Mac's Keychain

This asks for the token twice and keeps it out of your shell history:

```bash
security add-generic-password -U -a "$USER" -s naradi-connector -T /usr/bin/security -w
```

## 3. Add the connector to Claude

In the Claude desktop app: **Settings → Developer → Edit Config**. Add
`naradi` inside `mcpServers`, keeping anything already there. Use your
homelab's address and the full path to this folder:

```json
{
  "mcpServers": {
    "naradi": {
      "command": "/usr/bin/python3",
      "args": ["/Users/YOU/Development/Naradi/connector/naradi_connector.py"],
      "env": { "NARADI_URL": "http://HOMELAB-ADDRESS:30080" }
    }
  }
}
```

Quit Claude completely and open it again. Ask: "what was today's lift?"

The connector reads what has been imported, so upload the spreadsheet on
Fitness → Import first.

## Network

The `:30080` address is plain HTTP. On your home network the token travels
unencrypted; use the homelab's Tailscale address to have it encrypted.

## Turning it off

Remove `naradi` from the config, or delete the secret and redeploy:

```bash
kubectl delete secret naradi-connector-secret
```

To change the token, delete the secret and repeat steps 1 and 2.

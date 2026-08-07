#!/usr/bin/env python3
"""
Telecharge le .shortcut NON SIGNE (plist binaire) depuis un lien iCloud Shortcuts.

Usage:
    python3 dl_shortcut.py <id-ou-url-icloud> [dossier-sortie]

Exemples:
    python3 dl_shortcut.py 1601150b39a74ed48f553af8f3e29611
    python3 dl_shortcut.py https://www.icloud.com/shortcuts/1601150b39a74ed48f553af8f3e29611 ~/Documents

Produit:
    <nom>.plist       plist binaire brut (importable / analysable)
    <nom>.xml         meme contenu converti en XML lisible
    <nom>.record.json reponse brute de l'API (utile pour debug)
"""

import json
import os
import plistlib
import re
import sys
import urllib.error
import urllib.request

API = "https://www.icloud.com/shortcuts/api/records/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "\
     "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def extract_id(arg):
    """Accepte un ID nu, une URL /shortcuts/<id>, ou un UUID avec tirets."""
    m = re.search(r"([0-9a-fA-F]{32}|[0-9a-fA-F-]{36})", arg.strip())
    if not m:
        sys.exit("ID introuvable dans: %r" % arg)
    return m.group(1).replace("-", "").lower()


def safe_name(s):
    s = re.sub(r"[^\w\s.-]", "", s, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", s) or "shortcut"


def fetch_record(sid):
    try:
        return json.loads(http_get(API + sid))
    except urllib.error.HTTPError as e:
        sys.exit("API HTTP %s — lien prive, supprime ou ID invalide." % e.code)
    except urllib.error.URLError as e:
        sys.exit("Reseau indisponible: %s" % e.reason)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip())

    sid = extract_id(sys.argv[1])
    outdir = os.path.expanduser(sys.argv[2]) if len(sys.argv) > 2 else "."
    os.makedirs(outdir, exist_ok=True)

    print("→ interrogation de l'API pour %s ..." % sid)
    rec = fetch_record(sid)

    fields = rec.get("fields", {})
    if "shortcut" not in fields:
        sys.exit("Ce record ne contient pas de champ 'shortcut' "
                 "(cles: %s)" % ", ".join(fields))

    name = fields.get("name", {}).get("value", "shortcut")
    asset = fields["shortcut"]["value"]
    expected = asset.get("size")
    url = asset["downloadURL"].replace("${f}", "s.plist")

    base = os.path.join(outdir, safe_name(name))
    with open(base + ".record.json", "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)

    print("→ nom      : %s" % name)
    print("→ signature: %s" % fields.get("signingStatus", {}).get("value", "?"))
    print("→ taille   : %s octets attendus" % expected)
    print("→ telechargement du plist non signe ...")

    try:
        data = http_get(url)
    except urllib.error.HTTPError as e:
        sys.exit("Telechargement HTTP %s — le lien a probablement expire.\n"
                 "Relance simplement le script, il en regenere un." % e.code)

    if expected and len(data) != expected:
        print("   ! taille inattendue: %d recu / %d annonce" % (len(data), expected))

    if not data.startswith(b"bplist00"):
        sys.exit("Le fichier recu n'est pas un plist binaire (debut: %r)" % data[:16])

    with open(base + ".plist", "wb") as f:
        f.write(data)

    pl = plistlib.loads(data)
    actions = pl.get("WFWorkflowActions", [])

    with open(base + ".xml", "wb") as f:
        plistlib.dump(pl, f, fmt=plistlib.FMT_XML)

    print("\n✅ %d octets, %d actions" % (len(data), len(actions)))
    print("   %s.plist" % base)
    print("   %s.xml" % base)
    print("   %s.record.json" % base)

    print("\nActions:")
    for i, a in enumerate(actions, 1):
        ident = a.get("WFWorkflowActionIdentifier", "?")
        print("  %3d. %s" % (i, ident.replace("is.workflow.actions.", "")))


if __name__ == "__main__":
    main()

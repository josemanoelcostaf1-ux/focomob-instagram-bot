"""
Renova o token de acesso do Instagram antes que ele expire (~60 dias) e grava o novo
valor direto no secret IG_ACCESS_TOKEN do repositório, via API do GitHub.

A API do Instagram permite trocar um token de longa duração por outro novo (também
válido por ~60 dias) desde que o atual ainda não tenha expirado e tenha pelo menos
24 horas — por isso rodamos isso semanalmente, bem dentro dessa janela.

Precisa do secret GH_PAT: um Personal Access Token do GitHub com permissão de
"Secrets: Read and write" nesse repositório (veja o README).
"""
import base64
import os
import sys

import requests
from nacl import encoding, public

GRAPH = "https://graph.instagram.com"

REPO = os.environ.get("GITHUB_REPOSITORY", "")
GH_PAT = os.environ.get("GH_PAT", "")
CURRENT_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")

GITHUB_API = "https://api.github.com"
GITHUB_HEADERS_BASE = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def refresh_ig_token(token: str):
    r = requests.get(
        f"{GRAPH}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Erro ao renovar token ({r.status_code}): {r.text}")
    data = r.json()
    return data["access_token"], data.get("expires_in")


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def update_github_secret(name: str, value: str):
    headers = {**GITHUB_HEADERS_BASE, "Authorization": f"Bearer {GH_PAT}"}

    key_resp = requests.get(
        f"{GITHUB_API}/repos/{REPO}/actions/secrets/public-key", headers=headers, timeout=30
    )
    if not key_resp.ok:
        raise RuntimeError(f"Erro ao buscar chave pública do repositório ({key_resp.status_code}): {key_resp.text}")
    key_data = key_resp.json()

    encrypted_value = encrypt_secret(key_data["key"], value)

    put_resp = requests.put(
        f"{GITHUB_API}/repos/{REPO}/actions/secrets/{name}",
        headers=headers,
        json={"encrypted_value": encrypted_value, "key_id": key_data["key_id"]},
        timeout=30,
    )
    if not put_resp.ok:
        raise RuntimeError(f"Erro ao atualizar o secret {name} ({put_resp.status_code}): {put_resp.text}")


def main():
    if not CURRENT_TOKEN or not GH_PAT or not REPO:
        print("IG_ACCESS_TOKEN, GH_PAT ou GITHUB_REPOSITORY ainda não configurados — nada a fazer.")
        return

    try:
        new_token, expires_in = refresh_ig_token(CURRENT_TOKEN)
    except Exception as e:
        print(f"[ERRO] Não foi possível renovar o token: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        update_github_secret("IG_ACCESS_TOKEN", new_token)
    except Exception as e:
        print(f"[ERRO] Token renovado na Meta, mas falhou ao salvar no GitHub: {e}", file=sys.stderr)
        sys.exit(1)

    days = (expires_in or 0) // 86400
    print(f"Token renovado e salvo com sucesso. Validade: ~{days} dias.")


if __name__ == "__main__":
    main()

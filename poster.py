"""
Publica no Instagram da Focomob os itens de queue.json cuja data/hora já chegou.
Tipos: "reel" (vídeo 9:16), "image" (foto única) e "carousel" (várias imagens em `media`: lista).
Usa a Instagram API com Instagram Login (graph.instagram.com). Precisa de IG_USER_ID e IG_ACCESS_TOKEN
(Secrets do GitHub Actions). O estado (o que já foi publicado) fica em state.json, sem banco de dados.

DRY_RUN=1 só mostra o que seria enviado (não chama a API).
Se qualquer item falhar, o job termina com erro (workflow vermelho) — diferente do robô do Seu Zé, onde falha silenciosa
deixava o job verde.
"""
import datetime
import json
import os
import pathlib
import sys
import time

import requests

REPO = os.environ.get("GITHUB_REPOSITORY", "SEU_USUARIO/focomob-instagram-bot")
BRANCH = os.environ.get("REPO_BRANCH", "main")
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"

HERE = pathlib.Path(__file__).parent
QUEUE_PATH = HERE / "queue.json"
STATE_PATH = HERE / "state.json"
GRAPH = "https://graph.instagram.com/v21.0"

IG_USER_ID = os.environ.get("IG_USER_ID", "")
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
DRY = os.environ.get("DRY_RUN") == "1"


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def url(rel):
    return rel if rel.startswith("http") else f"{RAW}/{rel}"


def scrub(text):
    """Tira segredos de mensagens de erro (state.json é público no GitHub)."""
    for secret in (TOKEN, IG_USER_ID):
        if secret:
            text = text.replace(secret, "***")
    return text


def call(method, path, **params):
    params["access_token"] = TOKEN
    if DRY:
        shown = {k: v for k, v in params.items() if k != "access_token"}
        print(f"  [dry-run] {method} {path} {shown}")
        return {"id": "DRY", "status_code": "FINISHED"}
    r = requests.request(method, f"{GRAPH}/{path}", **({"params": params} if method == "GET" else {"data": params}), timeout=60)
    if not r.ok:
        raise RuntimeError(f"{method} {path} ({r.status_code}): {r.text}")
    return r.json()


def wait_ready(container_id, tries=36, every=10):
    """Vídeo leva alguns instantes para o Meta processar: espera status FINISHED (até ~6 min)."""
    for _ in range(tries):
        status = call("GET", container_id, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {container_id} terminou com status {status}")
        time.sleep(every)
    raise RuntimeError(f"container {container_id} não ficou pronto a tempo")


def build_container(item):
    t, cap = item["type"], item.get("caption", "")
    if t == "reel":
        extra = {"cover_url": url(item["cover"])} if item.get("cover") else {}  # capa validada (imagem em media/)
        return call("POST", f"{IG_USER_ID}/media", media_type="REELS", video_url=url(item["media"]), caption=cap, share_to_feed="true", **extra)["id"]
    if t == "image":
        return call("POST", f"{IG_USER_ID}/media", image_url=url(item["media"]), caption=cap)["id"]
    if t == "story":  # story: imagem 1080x1920 em JPEG, sem legenda
        return call("POST", f"{IG_USER_ID}/media", media_type="STORIES", image_url=url(item["media"]))["id"]
    if t == "carousel":
        kids = [call("POST", f"{IG_USER_ID}/media", image_url=url(m), is_carousel_item="true")["id"] for m in item["media"]]
        return call("POST", f"{IG_USER_ID}/media", media_type="CAROUSEL", children=",".join(kids), caption=cap)["id"]
    raise ValueError(f"tipo desconhecido: {t}")


def main():
    if not DRY and (not IG_USER_ID or not TOKEN):
        print("IG_USER_ID/IG_ACCESS_TOKEN ainda não configurados nos secrets — nada a fazer.")
        return

    queue, state = load(QUEUE_PATH, []), load(STATE_PATH, {})
    esperar_ate_min = int(os.environ.get("WAIT_MIN", "0"))
    if esperar_ate_min and not DRY:
        # O agendador do GitHub atrasa (às vezes horas). Os gatilhos começam ANTES do horário e este trecho espera até o
        # horário exato do próximo item aprovado que vence dentro de WAIT_MIN minutos, para publicar pontualmente.
        agora = datetime.datetime.now(datetime.timezone.utc)
        proximos = [datetime.datetime.fromisoformat(i["date"].replace("Z", "+00:00")) for i in queue
                    if i.get("approved") and not state.get(i["id"], {}).get("posted")]
        proximos = [d for d in proximos if agora < d <= agora + datetime.timedelta(minutes=esperar_ate_min)]
        if proximos:
            alvo = min(proximos)
            falta = (alvo - agora).total_seconds() + 3
            print(f"Esperando {falta:.0f}s até {alvo.isoformat()} para publicar no horário.")
            time.sleep(max(0, falta))
    now = datetime.datetime.now(datetime.timezone.utc)
    errors = 0
    for item in queue:
        entry = state.setdefault(item["id"], {})
        if entry.get("posted"):
            continue
        if not item.get("approved"):  # regra do José: nada é publicado sem aprovação explícita dele
            continue
        if datetime.datetime.fromisoformat(item["date"].replace("Z", "+00:00")) > now:
            continue
        try:
            print(f"Publicando {item['id']} ({item['type']})")
            cid = build_container(item)
            wait_ready(cid)
            res = call("POST", f"{IG_USER_ID}/media_publish", creation_id=cid)
            entry.pop("last_error", None)
            entry.update(posted=True, media_id=res.get("id"), posted_at=now.isoformat())
            print(f"[OK] {item['id']} publicado (media {res.get('id')})")
        except Exception as e:  # um erro não derruba o resto da fila, mas o job termina vermelho
            errors += 1
            entry["last_error"] = scrub(str(e))[:500]
            print(f"[ERRO] {item['id']}: {scrub(str(e))}", file=sys.stderr)
    if not DRY:
        save(STATE_PATH, state)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()

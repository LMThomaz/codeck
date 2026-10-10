#!/usr/bin/env bash
# O .dmg do Commitdeck para macOS, feito no Mac e publicado — o runner de macOS do GitHub conta dez vezes na cota
# gratuita, então o Mac sai daqui e só o Windows sai do Actions (.github/workflows/release-windows.yml).
#
#   scripts/release-macos.sh            gera e publica
#   scripts/release-macos.sh --dry-run  gera o .dmg; não publica
#
# Publica o que está na main (árvore limpa, commit já no origin/main), na versão do arquivo VERSION (x.y.z+N),
# a mesma do Windows. Destinos:
#   · site da ThomSoft: downloads/commitdeck/<dmg> + latest.json (o canal público que o app consulta)
#   · GitHub Releases (privado): tag v<x.y.z>-<N>, como histórico
# Credenciais do FTP do site — as mesmas do Chefinho/LuriSystem:
#   · servidor e usuário em ~/.config/thomsoft/downloads.env (DOWNLOADS_FTP_SERVER, DOWNLOADS_FTP_USER)
#   · a senha no Keychain (serviço thomsoft-downloads-ftp); nunca em arquivo nem na linha de comando.
set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *) echo "argumento desconhecido: $arg" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_URL="${DOWNLOADS_BASE_URL:-https://thomsoft.com.br/downloads}"
CHANNEL=commitdeck
KEYCHAIN_SERVICE=thomsoft-downloads-ftp
CONFIG="$HOME/.config/thomsoft/downloads.env"

say() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname)" = Darwin ] || fail "Só no macOS."
for tool in jq lftp create-dmg openssl gh; do command -v "$tool" >/dev/null || fail "Falta o $tool (brew install $tool)."; done

cd "$ROOT"
line="$(sed -nE 's/^([0-9]+\.[0-9]+\.[0-9]+)\+([0-9]+)$/\1 \2/p' VERSION)"
[ -n "$line" ] || fail "VERSION precisa ser x.y.z+N"
read -r VERSION BUILD <<< "$line"
TAG="v$VERSION-$BUILD"
if [ "$DRY_RUN" = false ]; then
  [ -z "$(git status --porcelain)" ] || fail "Há mudanças não commitadas. Publique só o que está na main."
  git fetch -q origin main
  git merge-base --is-ancestor HEAD origin/main || fail "O commit atual não está no origin/main. Faça o push antes."
fi
say "Commitdeck $VERSION (build $BUILD) — $(git rev-parse --short HEAD)"

if [ "$DRY_RUN" = false ]; then
  [ -f "$CONFIG" ] || fail "Crie $CONFIG com DOWNLOADS_FTP_SERVER e DOWNLOADS_FTP_USER (ver o topo deste script)."
  # shellcheck source=/dev/null
  source "$CONFIG"
  : "${DOWNLOADS_FTP_SERVER:?falta em $CONFIG}" "${DOWNLOADS_FTP_USER:?falta em $CONFIG}"
  if ! LFTP_PASSWORD="$(security find-generic-password -s "$KEYCHAIN_SERVICE" -a "$DOWNLOADS_FTP_USER" -w 2>/dev/null)"; then
    say "Senha do FTP ($DOWNLOADS_FTP_USER) — fica guardada no Keychain"
    security add-generic-password -U -s "$KEYCHAIN_SERVICE" -a "$DOWNLOADS_FTP_USER" -l "ThomSoft — FTP dos downloads" -w
    LFTP_PASSWORD="$(security find-generic-password -s "$KEYCHAIN_SERVICE" -a "$DOWNLOADS_FTP_USER" -w)"
  fi
  export LFTP_PASSWORD
  # O servidor é um IP com certificado *.hstgr.io: a cadeia é conferida aqui e o lftp dispensa só o hostname.
  cert="$(mktemp)"
  openssl s_client -starttls ftp -connect "$DOWNLOADS_FTP_SERVER:21" -verify_return_error -verify 5 \
    </dev/null 2>/dev/null | openssl x509 > "$cert" || fail "Certificado do FTP não validou."
  openssl x509 -in "$cert" -noout -checkend 0 >/dev/null || fail "Certificado do FTP vencido."
  openssl x509 -in "$cert" -noout -ext subjectAltName | grep -q 'DNS:\*\.hstgr\.io' || fail "Certificado do FTP não é da Hostinger."
fi

lftp_run() {
  lftp -u "$DOWNLOADS_FTP_USER" --env-password "ftp://$DOWNLOADS_FTP_SERVER" -e "
    set ftp:ssl-force true;
    set ftp:ssl-protect-data true;
    set ssl:verify-certificate true;
    set ssl:check-hostname false;
    set ftp:passive-mode true;
    set net:max-retries 3;
    set net:timeout 30;
    set net:reconnect-interval-base 5;
    set cmd:fail-exit true;
    $1
    bye"
}

say "Build"
bash scripts/build-macos.sh --no-install
out="$ROOT/dist/release-macos"
rm -rf "$out"; mkdir -p "$out/stage"
cp -R "$ROOT/dist/Commitdeck.app" "$out/stage/"
ln -s /Applications "$out/stage/Aplicativos"
dmg="$out/Commitdeck-$VERSION-$BUILD.dmg"
create-dmg --volname "Commitdeck" --volicon macos/AppIcon.icns \
  --window-pos 200 120 --window-size 600 380 --icon-size 104 --text-size 13 \
  --icon "Commitdeck.app" 160 180 --hide-extension "Commitdeck.app" --icon "Aplicativos" 440 180 \
  --no-internet-enable "$dmg" "$out/stage/" >/dev/null
echo "✓ $dmg ($(du -h "$dmg" | cut -f1))"

if [ "$DRY_RUN" = true ]; then say "Ensaio: o .dmg está em $out — nada foi publicado."; exit 0; fi

# O .dmg primeiro, o latest.json por último — só a parte do Mac; a do Windows fica como o CI a deixou.
say "Publicando no site"
rm -f "$out/current.json"
if lftp_run "cd /$CHANNEL; cls -1" 2>/dev/null | grep -qx 'latest.json'; then
  lftp_run "cd /$CHANNEL; lcd $out; get latest.json -o current.json" || fail "Não li o latest.json publicado — nada foi enviado."
  jq -e 'type == "object"' "$out/current.json" >/dev/null || fail "O latest.json publicado não é JSON — nada foi enviado."
else
  echo '{}' > "$out/current.json"   # primeira publicação
fi
name="$(basename "$dmg")"
jq --arg url "$BASE_URL/$CHANNEL/$name" \
   --arg sha "$(shasum -a 256 "$dmg" | cut -d' ' -f1)" \
   --argjson size "$(stat -f %z "$dmg")" \
   --arg version "$VERSION" --argjson build "$BUILD" \
   --arg notes "$(git log -1 --format=%s)" \
   --arg date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
   '.productId = "commitdeck"
    | .macos = {url: $url, sha256: $sha, size: $size, version: $version, build: $build}
    | .notes = $notes | .publishedAt = $date
    | ([.windows, .macos] | map(select(. != null)) | max_by(.build)) as $n
    | .version = $n.version | .build = $n.build' \
   "$out/current.json" > "$out/latest.json"
lftp_run "mkdir -p -f /$CHANNEL; cd /$CHANNEL; put $dmg; put $out/latest.json;"
old="$(lftp_run "cd /$CHANNEL; cls -1" | sed -nE 's/^Commitdeck-[0-9.]+-([0-9]+)\.dmg$/\1/p' | sort -un | awk '{a[NR]=$0} END {for (i = 1; i <= NR - 2; i++) print a[i]}')"
for b in $old; do lftp_run "cd /$CHANNEL; glob -a rm -f Commitdeck-*-$b.dmg;" || true; done
got="$(curl -fsS "$BASE_URL/$CHANNEL/latest.json?t=$(date +%s)" | jq -r .macos.build)"
[ "$got" = "$BUILD" ] || fail "O site ainda serve o build $got."
curl -fsSI "$BASE_URL/$CHANNEL/$name" >/dev/null || fail "O .dmg não responde no site."

# Ponte para quem ainda tem o PR Pilot (nome antigo): esse app lê downloads/pr-pilot/latest.json e só aceita
# instalador chamado PR-Pilot-*. O mesmo .dmg vai para lá com esse nome; instalado, o app se renomeia para
# Commitdeck.app e adota a pasta de dados antiga. Pode sair quando ninguém mais estiver no PR Pilot.
LEGACY=pr-pilot
legacy="$out/PR-Pilot-$VERSION-$BUILD.dmg"
cp "$dmg" "$legacy"
say "Ponte no canal antigo ($LEGACY)"
rm -f "$out/legacy-current.json"
if lftp_run "cd /$LEGACY; cls -1" 2>/dev/null | grep -qx 'latest.json'; then
  lftp_run "cd /$LEGACY; lcd $out; get latest.json -o legacy-current.json" || fail "Não li o latest.json do canal antigo."
  jq -e 'type == "object"' "$out/legacy-current.json" >/dev/null || fail "O latest.json do canal antigo não é JSON."
else
  echo '{}' > "$out/legacy-current.json"
fi
jq --arg url "$BASE_URL/$LEGACY/$(basename "$legacy")" \
   --arg sha "$(shasum -a 256 "$legacy" | cut -d' ' -f1)" \
   --argjson size "$(stat -f %z "$legacy")" \
   --arg version "$VERSION" --argjson build "$BUILD" \
   --arg notes "Agora se chama Commitdeck. $(git log -1 --format=%s)" \
   --arg date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
   '.productId = "pr-pilot"
    | .macos = {url: $url, sha256: $sha, size: $size, version: $version, build: $build}
    | .notes = $notes | .publishedAt = $date
    | ([.windows, .macos] | map(select(. != null)) | max_by(.build)) as $n
    | .version = $n.version | .build = $n.build' \
   "$out/legacy-current.json" > "$out/legacy-latest.json"
lftp_run "mkdir -p -f /$LEGACY; cd /$LEGACY; put $legacy; put $out/legacy-latest.json -o latest.json;"
old="$(lftp_run "cd /$LEGACY; cls -1" | sed -nE 's/^PR-Pilot-[0-9.]+-([0-9]+)\.dmg$/\1/p' | sort -un | awk '{a[NR]=$0} END {for (i = 1; i <= NR - 2; i++) print a[i]}')"
for b in $old; do lftp_run "cd /$LEGACY; glob -a rm -f PR-Pilot-*-$b.dmg;" || true; done

say "GitHub Releases ($TAG)"
gh release view "$TAG" >/dev/null 2>&1 || gh release create "$TAG" --title "Commitdeck $VERSION (build $BUILD)" \
  --notes "$(git log -1 --format=%B)" --target "$(git rev-parse HEAD)"
gh release upload "$TAG" "$dmg" "$out/latest.json" --clobber
say "Publicado: $BASE_URL/$CHANNEL/latest.json"

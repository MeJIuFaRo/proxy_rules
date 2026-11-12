# proxy_rules

Списки IPv4 для MikroTik: адреса сервисов, которые должны идти через VPN.

## Address-list `VPN`

GitHub Actions (`.github/workflows/update-ip-lists.yml`) каждый день в 03:17 UTC
запускает `scripts/update_ip_lists.py` и коммитит изменения в `lists/`.

| Источник | Откуда берутся адреса |
|---|---|
| Cloudflare | https://www.cloudflare.com/ips-v4 |
| Google | https://www.gstatic.com/ipranges/goog.txt |
| Meta | префиксы, анонсируемые AS32934, AS63293, AS54115 (RIPEstat) |
| ChatGPT | префиксы AS401864 (OpenAI) + текущие IP хостов ChatGPT/OpenAI |
| Claude | [документация Anthropic](https://platform.claude.com/docs/en/api/ip-addresses) (входящие и исходящие IPv4, без «Phased out») + префиксы AS399358, AS400243, AS401551 + текущие IP хостов Claude |

Хосты, которые резолвятся в /32, перечислены в `SOURCES` в скрипте. Большая часть
ChatGPT стоит за Cloudflare и уже покрыта его диапазонами, поэтому в итоговый
список попадают только адреса вне Cloudflare (например, голосовой режим на LiveKit).
DNS резолвится с раннера GitHub в США; для anycast-адресов это не важно.

Файлы в `lists/`:

- `<источник>.txt` — CIDR одного источника;
- `vpn.txt` — общий список без дублей (сеть, уже покрытая предыдущим источником, пропускается);
- `vpn.rsc` — скрипт RouterOS, синхронизирующий `/ip firewall address-list` `VPN`.

Если источник не скачался, его прежний `.txt` остаётся и используется при сборке,
а запуск workflow помечается как неудачный.

### Как `vpn.rsc` обновляет список

Скрипт трогает только записи с комментарием `proxy_rules: …`; добавленные вручную
записи в `VPN` остаются. Порядок:

1. все свои записи помечаются `proxy_rules: stale`;
2. каждый адрес добавляется, а если он уже есть — с него снимается метка `stale`;
3. оставшиеся `stale` удаляются.

Список не пустеет во время импорта, а дубль с ручной записью не прерывает импорт.

## Загрузка на MikroTik (приватный репозиторий)

`raw.githubusercontent.com` для приватного репозитория требует токен, поэтому файл
берётся через GitHub API с fine-grained токеном: только этот репозиторий,
право **Contents: Read-only**. Токен хранится в конфигурации роутера открытым текстом.

```routeros
/system script add name=vpn-list-update policy=ftp,read,write,test source={
  /tool fetch url="https://api.github.com/repos/MeJIuFaRo/proxy_rules/contents/lists/vpn.rsc?ref=main" \
    http-header-field="Authorization: Bearer <GITHUB_TOKEN>,Accept: application/vnd.github.raw,User-Agent: mikrotik" \
    dst-path=vpn.rsc
  :delay 2s
  /import file-name=vpn.rsc
}
/system scheduler add name=vpn-list-update interval=1d start-time=07:00:00 on-event=vpn-list-update
```

Если `fetch` завершится ошибкой, скрипт остановится до `/import` и список не изменится.

Записи из прежних списков `CLOUDFLARE` и `GOOGLE` этим скриптом не удаляются;
уберите их вручную, если они больше не нужны:

```routeros
/ip firewall address-list remove [find where list="CLOUDFLARE" or list="GOOGLE"]
```

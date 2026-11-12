# proxy_rules

Правила для MikroTik: какой трафик идёт через VPN. Роутер раз в сутки скачивает
два файла и импортирует их:

| Файл | Что делает на роутере | Откуда берётся |
|---|---|---|
| `lists/vpn.rsc` | `/ip firewall address-list` `VPN` — IPv4-подсети сервисов | собирает GitHub Actions из публичных источников |
| `lists/dns.rsc` | `/ip dns static type=FWD forward-to=VPN match-subdomain=yes address-list=VPN` | собирает GitHub Actions из `dns/vpn.txt`, который правится руками |

Оба `.rsc` генерируются — не правьте их вручную.

## Домены: `dns/vpn.txt`

Один домен на строку, поддомены включаются автоматически. Чтобы добавить домен,
допишите его в файл и закоммитьте в `main`: workflow соберёт `lists/dns.rsc`
в течение пары минут, роутер подхватит его при следующем запуске.
Строка с ошибкой останавливает сборку, прежний `dns.rsc` остаётся.

На роутере для этих доменов запросы уходят на forwarder `VPN`
(`/ip dns forwarders`), а полученные IP попадают в address-list `VPN`.
Работает только для клиентов, которые используют DNS роутера (не DoH в браузере).

## IP-подсети: `lists/vpn.rsc`

| Источник | Откуда берутся адреса |
|---|---|
| Cloudflare | https://www.cloudflare.com/ips-v4 |
| Google | https://www.gstatic.com/ipranges/goog.txt |
| Meta | префиксы, анонсируемые AS32934, AS63293, AS54115 (RIPEstat) |
| ChatGPT | префиксы AS401864 (OpenAI) + текущие IP хостов ChatGPT/OpenAI |
| Claude | [документация Anthropic](https://platform.claude.com/docs/en/api/ip-addresses) (входящие и исходящие IPv4, без «Phased out») + префиксы AS399358, AS400243, AS401551 + текущие IP хостов Claude |
| Discord | блоки адресов организации Discord (`ORG-DI90-RIPE`) в базе RIPE — голосовые и видеосерверы `66.22.192.0/18` |

Хосты, которые резолвятся в /32, перечислены в `SOURCES` в `scripts/update_ip_lists.py`.
Сеть, уже покрытая источником выше по таблице, второй раз не добавляется.
Если источник не скачался, используется его прежний `lists/<источник>.txt`.

## Как `.rsc` обновляют роутер

Оба файла трогают только свои записи — с комментарием `proxy_rules: …`:

1. все свои записи помечаются `proxy_rules: stale`;
2. каждая запись из файла добавляется, а если уже есть — с неё снимается метка;
3. оставшиеся `stale` удаляются.

Списки не пустеют во время импорта. Ручные записи не удаляются, но в `dns.rsc`
FWD-запись с тем же именем, что в `dns/vpn.txt`, переходит под управление
репозитория: ей выставляются `forward-to=VPN`, `address-list=VPN`, комментарий.
Если удалить домен из `dns/vpn.txt`, его запись будет удалена с роутера.

`dns.rsc` ничего не меняет, если на роутере нет forwarder'а `VPN`.

Кроме доменов, `dns.rsc` задаёт общие настройки DNS и блок-листы рекламы
(константы `DNS_SETTINGS` и `ADLISTS` в `scripts/build_dns_rsc.py`):

```routeros
/ip dns set address-list-extra-time=1d allow-remote-requests=yes cache-size=24576KiB
/ip dns adlist add url=https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts ssl-verify=no
/ip dns adlist add url=https://adguardteam.github.io/HostlistsRegistry/assets/filter_1.txt ssl-verify=no
```

Adlist добавляется, только если такого URL на роутере ещё нет, и скриптом не удаляется.
`allow-remote-requests=yes` делает роутер DNS-сервером: закройте 53/udp и 53/tcp
с WAN в firewall, иначе он станет открытым резолвером.

## Установка на MikroTik

1. Создайте fine-grained токен GitHub: только репозиторий `MeJIuFaRo/proxy_rules`,
   право **Contents: Read-only**. Токен хранится в конфигурации роутера открытым текстом.
2. В `mikrotik/proxy-rules-update.rsc` замените `<GITHUB_TOKEN>` и импортируйте файл
   на роутер (или вставьте его содержимое в терминал). Он создаст скрипт
   `proxy-rules-update` и ежедневное расписание на 07:00.
3. Первый запуск вручную и проверка:

```routeros
/system script run proxy-rules-update
/log print where message~"proxy_rules"
/ip firewall address-list print count-only where list=VPN
/ip dns static print count-only where comment~"proxy_rules"
```

Если скачивание или импорт файла не удались, в логе будет
`update failed, previous rules kept`, а правила останутся прежними.

## GitHub Actions

`.github/workflows/update-ip-lists.yml` запускается каждый день в 03:17 UTC,
вручную и при пуше в `main` изменений в `dns/` или `scripts/`. Запуск помечается
неудачным, если какой-то источник или `dns/vpn.txt` не удалось обработать;
успешные части при этом всё равно коммитятся.

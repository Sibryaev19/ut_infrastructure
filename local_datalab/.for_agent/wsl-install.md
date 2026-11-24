# Установка WSL/Docker — журнал (2026-11-24)

## ИТОГ: НЕ УДАЛОСЬ — переезжаем на комп с Ubuntu
restorehealth отработал успешно, но payload подсистемы так и не восстановился
(System32\lxss — только `lib`, драйверов нет; enable-feature ×2 и
`wsl --install --no-distribution` после ребутов дают то же
WSL_E_WSL_OPTIONAL_COMPONENT_REQUIRED). Оставшийся запасной план для ноута —
ISO 19045: MCT → ISO → `dism /enable-feature /limitaccess /source:wim:E:\sources\install.esd:N`
(индекс своей редакции из `dism /get-wiminfo`). Но стенд строим на компе.

## Где остановились

## Что установлено/проверено
- Docker Desktop 4.100.1 — установлен (winget), демон не стартует из-за WSL.
- WSL: Store 3.0.1 → заменили на MSI **3.0.5** (`wsl.3.0.5.0.x64.msi` в
  Загрузках, ставится в `C:\Program Files\WSL`). Служба `WslService` есть,
  запускается (`net start wslservice`).
- Компоненты `Microsoft-Windows-Subsystem-Linux` и `VirtualMachinePlatform` —
  State: **Enabled** (через DISM; `Enable-WindowsOptionalFeature` молча не сработал).
- Виртуализация в BIOS — **Включено** (Ryzen 5 3550H, Диспетчер задач).
- `bcdedit /set hypervisorlaunchtype auto` — сделано, перезагрузки выполнялись
  (несколько полных shutdown/boot).

## Симптом (НЕ решён)
`wsl --status` / `-l -v` / любой запуск дистрибуции →
`WSL_E_WSL_OPTIONAL_COMPONENT_REQUIRED` — при этом:
- `wsl --version` работает (3.0.5),
- компоненты Enabled,
- служба запущена.
Важно: в `C:\Windows\System32\lxss` остался только `lib` — ключевых файлов
подсистемы (lxcore.sys и др.) нет. Вывод: **повреждено хранилище компонентов
Windows** (вероятно, система «чистилась» ранее — объясняет прошлую неудачу).

## Что пробовали и не помогло
- `wsl --install --no-distribution`, DISM enable-feature — «успех», но файлы не появились.
- `bcdedit hypervisorlaunchtype auto` — применён, не причина.
- MSI-переустановка WSL — служба появилась, ошибка осталась.

## План после restorehealth
1. `dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart`
2. `dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart`
3. Перезагрузка → `wsl --status` (MSI-версия) → `wsl --install --no-distribution` если надо.
4. Если не поможет: restorehealth с `/source` из смонтированного ISO Win10 19045
   (`/limitaccess /source:E:\sources\sxs`).
5. Когда `wsl --status` живой: Docker Desktop → «Engine running» →
   `docker run --rm hello-world`.
6. Заметка: если pull образов с Docker Hub упадёт (РФ) — добавить registry-mirrors
   в Docker Engine settings.

## Мелочи для удобства
- У пользователя глючит ввод заглавных латинских букв в PowerShell — команды
  давать в нижнем регистре или для копипасты.

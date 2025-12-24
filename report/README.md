# Отчёты и документы (docx через `docx`)

Нужен установленный Node.js (LTS) и зависимости из `package.json`.

## Установка зависимостей

```bash
npm install
```

## Генерация отчетов

```bash
npm run report:1
npm run report:2
npm run report:3
```

Файлы создаются в папке `docs/`.

## Руководство системному программисту

```bash
npm run sysprog
```

По умолчанию номер рабочего места `00`. Можно указать свой номер:

```bash
node report/generate_sysprog_manual.js 12
```


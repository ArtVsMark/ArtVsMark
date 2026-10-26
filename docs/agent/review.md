# Процедура внешнего взгляда: кем смотреть на изменение витрины

> **Читатель:** внешний взгляд — ревьюер изменения и поздний взгляд по слитому;
> и тот, кто правит, как взгляд смотрит.

Взгляд — общий шаг Engineering-Pipeline-Mechanisms (`step-review.yml`), позванный
тонким вызовом `.github/workflows/review.yml` (#345, шаг B). **Как смотреть** —
три захода, роли, форма ответа — канон механизмов:
[`docs/agent/review.md`](https://github.com/ArtVsMark/Engineering-Pipeline-Mechanisms/blob/96c2c93b52cd5a433e06a2984a0919e655ad9b73/docs/agent/review.md)
на коммите выпуска v1.11.0. Здесь он не пересказывается: пересказ разошёлся бы
с ним с первой правки
([022](https://github.com/ArtVsMark/Engineering-Incidents-Playbook/blob/main/rules/ru/022-one-canonical-document.md)).

Этот файл подставляется в задание взгляда **с общей ветки**, а не с головы
изменения: голову пишет тот, кого проверяют
([085](https://github.com/ArtVsMark/Engineering-Incidents-Playbook/blob/main/rules/ru/085-content-from-the-subject-is-untrusted-input-to-the-prompt.md)).
Правка файла действует со следующего изменения после слияния.

Свои у витрины три вещи: раздел ниже, таблица ролей
[`.rules/review-roles.json`](../../.rules/review-roles.json) и профили ролей —
раздел «Профили ролей взгляда» в [`roles.md`](roles.md).

## Что держит проект

Проект — **витрина профиля**: страница `README.md`, которую читает посетитель
профиля на GitHub, и сборка, которая её наполняет числами соседей
(`scripts/build_metrics.py`). Читай изменение по своду
[`CLAUDE.md`](../../CLAUDE.md); правила, на которые он ссылается, живут в
каталоге `ArtVsMark/Engineering-Incidents-Playbook`, а ответ витрины по каждому —
в `.rules/bindings.json`.

Что у витрины ломается чаще всего и чего машина не видит:

- **утверждение на странице, которое читатель не может проверить.** Число —
  только между маркерами `m:ключ`, которые пишет сборка; вписанное руками — дефект;
- **второй источник правды.** Список проектов — `projects.json`, ответ каталогу —
  `bindings.json`, источники свода — `.rules/sources.json`; копия в прозе
  устаревает молча;
- **два исхода вместо трёх.** Источник не ответил — это третий исход, а не «пусто»
  и не вчерашнее число
  ([039](https://github.com/ArtVsMark/Engineering-Incidents-Playbook/blob/main/rules/ru/039-three-outcomes-not-two.md));
- **починка признака без соседей.** Правка предиката, решающего больше одного
  случая, называет соседей строкой «Соседи:» в коммите
  ([195](https://github.com/ArtVsMark/Engineering-Incidents-Playbook/blob/main/rules/ru/195-a-narrowed-predicate-names-its-neighbour.md)).

Язык страницы — английский с русским пересказом в конце; всё служебное —
по-русски.
